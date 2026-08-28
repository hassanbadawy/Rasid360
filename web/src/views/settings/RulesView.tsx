import Heading from "@/components/ui/heading";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Rasid360Config } from "@/types/rasid360Config";
import { ViolationRule } from "@/types/violation";
import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import axios from "axios";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { LuPencil, LuPlus, LuTrash2, LuTriangleAlert } from "react-icons/lu";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import RuleEditDialog from "@/components/settings/RuleEditDialog";
import { StatusBarMessagesContext } from "@/context/statusbar-provider";

type RulesViewProps = {
  selectedCamera: string;
  setUnsavedChanges: (unsaved: boolean) => void;
};

const SEVERITY_STYLES: { [key: string]: string } = {
  low: "bg-secondary text-primary/70",
  medium: "bg-sky-500/20 text-sky-700 dark:text-sky-300",
  high: "bg-orange-500/20 text-orange-700 dark:text-orange-300",
  critical: "bg-destructive/20 text-destructive",
};

/** Plain-language summary of what a rule watches for, so the list is readable
 *  without opening each rule. */
function describeRule(rule: ViolationRule): string {
  switch (rule.type) {
    case "zone_sequence":
      return `${(rule.vehicle_types ?? []).join(", ") || "objects"} moving from ${(
        rule.from_zones ?? []
      ).join(" or ")} into ${rule.to_zone}`;
    case "sustained_condition":
      return `${rule.condition ?? ""}${
        rule.monitor_duration ? ` for ${rule.monitor_duration}s` : ""
      }${rule.speed_threshold ? ` above ${rule.speed_threshold} km/h` : ""}`;
    case "fall_down":
      return `person wider than ${rule.width_height_ratio}x their height for ${rule.min_duration}s`;
    default:
      return rule.condition ?? rule.type;
  }
}

export default function RulesView({
  selectedCamera,
  setUnsavedChanges,
}: RulesViewProps) {
  const { t } = useTranslation(["views/settings"]);
  const { data: config, mutate: updateConfig } =
    useSWR<Rasid360Config>("config");

  const [editing, setEditing] = useState<ViolationRule | undefined>();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<ViolationRule | undefined>();
  const [saving, setSaving] = useState(false);
  const { addMessage } = useContext(StatusBarMessagesContext)!;

  const cameraConfig = useMemo(
    () => (selectedCamera ? config?.cameras?.[selectedCamera] : undefined),
    [config, selectedCamera],
  );

  // Rules come from the config *file*, not /api/config -- that serves the
  // running in-memory config, which does not reflect config/set writes until
  // Frigate restarts. Saving writes a camera's whole list at once, so reading
  // the in-memory copy would write back a stale list and drop any rule saved
  // since the last restart.
  const { data: fileRules, mutate: updateFileRules } = useSWR<{
    [camera: string]: ViolationRule[];
  }>("config/violations");

  // Authored objects.track, for the same reason the rules come from the file.
  const { data: fileTracked } = useSWR<{
    objects?: { track?: string[] };
    cameras?: Record<string, { objects?: { track?: string[] } } | undefined>;
  }>("config/file");

  const configRules = useMemo<ViolationRule[]>(
    () => (selectedCamera ? (fileRules?.[selectedCamera] ?? []) : []),
    [fileRules, selectedCamera],
  );
  const [rules, setRules] = useState<ViolationRule[]>([]);

  useEffect(() => {
    setRules(configRules);
  }, [configRules, selectedCamera]);

  // Every camera the rule could be moved to, with the zones and tracked
  // objects a rule on it is validated against.
  const ruleCameras = useMemo(
    () =>
      Object.entries(config?.cameras ?? {})
        .filter(([, c]) => c.enabled_in_config)
        .map(([name, c]) => ({
          name,
          zones: Object.keys(c.zones ?? {}),
          // The *authored* track list, from the config file -- not /api/config.
          // verify_objects_track() strips labels the model cannot produce and
          // runs AFTER verify_violation_rules(), so rules are validated against
          // what the file says. Reading the stripped runtime list would make the
          // dialog offer to re-add labels the config already has.
          trackedObjects:
            fileTracked?.cameras?.[name]?.objects?.track ??
            fileTracked?.objects?.track ??
            [],
          ruleNames: (fileRules?.[name] ?? []).map((r) => r.name),
        })),
    [config, fileRules, fileTracked],
  );

  // Every label the detection model can produce. Rules are not limited to what
  // a camera happens to track today -- picking an untracked one widens
  // objects.track on save.
  const modelObjects = useMemo(() => {
    const labels = new Set<string>();
    for (const detector of Object.values(config?.detectors ?? {})) {
      const map = (
        detector as { model?: { labelmap?: Record<string, string> } }
      ).model?.labelmap;
      for (const label of Object.values(map ?? {})) labels.add(label);
    }
    return [...labels].sort();
  }, [config]);

  useEffect(() => {
    document.title = `${t("rules.documentTitle")} - Rasid360`;
  }, [t]);

  // Rules are validated against this camera's zones and tracked objects when
  // the config is parsed, and config/set rolls the file back if that fails --
  // so a rejected save leaves the running config untouched.
  const persist = useCallback(
    async (
      next: ViolationRule[],
      successKey: string,
      // defaults to the camera the page is showing
      targetCamera?: string,
      // extra config to merge for that camera, e.g. a widened objects.track
      extraCameraConfig?: Record<string, unknown>,
      // rules for a camera the rule moved away from
      alsoWrite?: Record<string, ViolationRule[]>,
    ) => {
      const target = targetCamera ?? selectedCamera;
      if (!target) return;

      setSaving(true);
      try {
        const cameraPayload: Record<string, unknown> = {
          [target]: { violations: next, ...(extraCameraConfig ?? {}) },
        };

        for (const [cam, list] of Object.entries(alsoWrite ?? {})) {
          cameraPayload[cam] = { violations: list };
        }

        const response = await axios.put("config/set", {
          config_data: { cameras: cameraPayload },
          requires_restart: 1,
        });

        if (response.status === 200 && response.data.success !== false) {
          toast.success(t(successKey), { position: "top-center" });
          // only reflect locally when we wrote the camera being displayed
          if (target === selectedCamera) setRules(next);
          updateFileRules();
          updateConfig();
          setUnsavedChanges(false);
          addMessage(
            "rules_restart",
            t("rules.restartRequired"),
            undefined,
            "rules_settings",
          );
        } else {
          toast.error(response.data.message ?? t("rules.toast.error"), {
            position: "top-center",
          });
        }
      } catch (error) {
        const message =
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (error as any)?.response?.data?.message ?? t("rules.toast.error");
        toast.error(message, { position: "top-center" });
      } finally {
        setSaving(false);
      }
    },
    [
      selectedCamera,
      t,
      updateFileRules,
      updateConfig,
      setUnsavedChanges,
      addMessage,
    ],
  );

  const handleSave = useCallback(
    (rule: ViolationRule, targetCamera: string, newTracked: string[]) => {
      const movedCamera = targetCamera !== selectedCamera;

      // Rules on the destination camera, which is not necessarily this page's.
      const targetRules = movedCamera
        ? (fileRules?.[targetCamera] ?? [])
        : rules;

      const index = targetRules.findIndex((r) => r.name === editing?.name);
      const next = [...targetRules];
      if (index >= 0 && !movedCamera) next[index] = rule;
      else next.push(rule);

      // A label the rule needs but the camera does not track would be rejected
      // by verify_violation_rules, so widen objects.track in the same write.
      const target = ruleCameras.find((c) => c.name === targetCamera);
      const extra = newTracked.length
        ? {
            objects: {
              track: [...(target?.trackedObjects ?? []), ...newTracked],
            },
          }
        : undefined;

      // Moving a rule means dropping it from the camera it came from.
      const alsoWrite =
        movedCamera && editing
          ? { [selectedCamera]: rules.filter((r) => r.name !== editing.name) }
          : undefined;

      persist(next, "rules.toast.saved", targetCamera, extra, alsoWrite);
    },
    [rules, editing, persist, selectedCamera, fileRules, ruleCameras],
  );

  const handleToggle = useCallback(
    (rule: ViolationRule, enabled: boolean) => {
      const next = rules.map((r) =>
        r.name === rule.name ? { ...r, enabled } : r,
      );
      persist(next, enabled ? "rules.toast.enabled" : "rules.toast.disabled");
    },
    [rules, persist],
  );

  const handleDelete = useCallback(() => {
    if (!deleting) return;
    persist(
      rules.filter((r) => r.name !== deleting.name),
      "rules.toast.deleted",
    );
    setDeleting(undefined);
  }, [deleting, rules, persist]);

  if (!config) {
    return <ActivityIndicator />;
  }

  return (
    <>
      <Toaster position="top-center" closeButton={true} />

      <div className="flex size-full flex-col md:flex-row">
        <div className="scrollbar-container order-last mb-10 mt-2 flex h-full w-full flex-col overflow-y-auto rounded-lg border-[1px] border-secondary-foreground bg-background_alt p-2 md:order-none md:mb-0 md:mr-2 md:mt-0">
          <div className="flex flex-row items-center justify-between">
            <Heading as="h3" className="my-2">
              {t("rules.title")}
            </Heading>
            <Button
              variant="select"
              disabled={!selectedCamera || saving}
              onClick={() => {
                setEditing(undefined);
                setDialogOpen(true);
              }}
            >
              <LuPlus className="mr-2 size-4" />
              {t("rules.add")}
            </Button>
          </div>

          <div className="mb-4 max-w-5xl text-sm text-primary/70">
            {t("rules.desc")}
          </div>

          <Separator className="my-2 flex bg-secondary" />

          {Object.keys(cameraConfig?.zones ?? {}).length === 0 && (
            <div className="my-4 flex items-center gap-2 rounded-md bg-secondary p-3 text-sm">
              <LuTriangleAlert className="size-4 shrink-0 text-danger" />
              <span>{t("rules.noZonesWarning")}</span>
            </div>
          )}

          {rules.length === 0 ? (
            <div className="my-8 text-center text-sm text-primary/60">
              {t("rules.empty", { camera: selectedCamera })}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {rules.map((rule) => (
                <div
                  key={rule.name}
                  className="flex flex-row items-center justify-between gap-4 rounded-lg bg-secondary p-3"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium smart-capitalize">
                        {rule.name}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs ${
                          SEVERITY_STYLES[rule.severity ?? "medium"]
                        }`}
                      >
                        {rule.severity ?? "medium"}
                      </span>
                      {!rule.enabled && (
                        <span className="rounded bg-background_alt px-1.5 py-0.5 text-xs text-primary/60">
                          {t("rules.disabled")}
                        </span>
                      )}
                    </div>
                    <div className="font-mono truncate text-xs text-primary/60">
                      {describeRule(rule)}
                    </div>
                    {rule.description && (
                      <div className="truncate text-xs text-primary/50">
                        {rule.description}
                      </div>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Switch
                      checked={rule.enabled}
                      disabled={saving}
                      aria-label={t("rules.toggle", { name: rule.name })}
                      onCheckedChange={(checked) => handleToggle(rule, checked)}
                    />
                    <Button
                      size="sm"
                      disabled={saving}
                      aria-label={t("rules.editRule", { name: rule.name })}
                      onClick={() => {
                        setEditing(rule);
                        setDialogOpen(true);
                      }}
                    >
                      <LuPencil className="size-4" />
                    </Button>
                    <Button
                      size="sm"
                      className="text-danger"
                      disabled={saving}
                      aria-label={t("rules.deleteRule", { name: rule.name })}
                      onClick={() => setDeleting(rule)}
                    >
                      <LuTrash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <RuleEditDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        rule={editing}
        camera={selectedCamera}
        cameras={ruleCameras}
        modelObjects={modelObjects}
        onSave={handleSave}
      />

      <AlertDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(undefined)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("rules.delete.title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("rules.delete.desc", { name: deleting?.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t("button.cancel", { ns: "common" })}
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white"
              onClick={handleDelete}
            >
              {t("button.delete", { ns: "common" })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
