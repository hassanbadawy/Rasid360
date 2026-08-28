import Heading from "@/components/ui/heading";
import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Toaster, toast } from "sonner";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import useSWR from "swr";
import axios from "axios";
import { Rasid360Config } from "@/types/rasid360Config";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import { StatusBarMessagesContext } from "@/context/statusbar-provider";
import { useTranslation } from "react-i18next";
import { useCameraFriendlyName } from "@/hooks/use-camera-friendly-name";
import { LuInfo } from "react-icons/lu";
import { cn } from "@/lib/utils";

type RecordingSettingsViewProps = {
  selectedCamera: string;
  setUnsavedChanges: React.Dispatch<React.SetStateAction<boolean>>;
};

// Retention modes Frigate accepts for a review-backed retention window.
const RETAIN_MODES = ["all", "motion", "active_objects"] as const;

/**
 * Every field this page can write, as a dot-path under a `record:` block.
 *
 * `kind` drives both the control and the coercion applied before the value is
 * sent -- config/set stores whatever JSON it is given, so a number field that
 * submits a string would write `days: "30"` into the YAML and fail validation.
 */
const FIELDS = [
  { path: "continuous.days", kind: "days", group: "storage" },
  { path: "motion.days", kind: "days", group: "storage" },
  { path: "alerts.retain.days", kind: "days", group: "alerts" },
  { path: "alerts.retain.mode", kind: "mode", group: "alerts" },
  { path: "alerts.pre_capture", kind: "seconds", group: "alerts" },
  { path: "alerts.post_capture", kind: "seconds", group: "alerts" },
  { path: "detections.retain.days", kind: "days", group: "detections" },
  { path: "detections.retain.mode", kind: "mode", group: "detections" },
  { path: "detections.pre_capture", kind: "seconds", group: "detections" },
  { path: "detections.post_capture", kind: "seconds", group: "detections" },
] as const;

type FieldPath = (typeof FIELDS)[number]["path"];

// Schema defaults from frigate/config/camera/record.py, used when neither the
// file nor a preset has set a value.
const SCHEMA_DEFAULTS: Record<FieldPath, string> = {
  "continuous.days": "0",
  "motion.days": "0",
  "alerts.retain.days": "10",
  "alerts.retain.mode": "motion",
  "alerts.pre_capture": "5",
  "alerts.post_capture": "5",
  "detections.retain.days": "10",
  "detections.retain.mode": "motion",
  "detections.pre_capture": "5",
  "detections.post_capture": "5",
};

const PRESETS: Record<string, Partial<Record<FieldPath, string>>> = {
  violationsOnly: {
    "continuous.days": "0",
    "motion.days": "0",
    "alerts.retain.days": "30",
    "alerts.retain.mode": "all",
    "detections.retain.days": "0",
  },
  motionBuffer: {
    "continuous.days": "0",
    "motion.days": "2",
    "alerts.retain.days": "30",
    "alerts.retain.mode": "all",
    "detections.retain.days": "10",
  },
  everything: {
    "continuous.days": "7",
    "motion.days": "14",
    "alerts.retain.days": "30",
    "alerts.retain.mode": "all",
    "detections.retain.days": "30",
  },
};

function readPath(source: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (acc, key) =>
        acc && typeof acc === "object"
          ? (acc as Record<string, unknown>)[key]
          : undefined,
      source,
    );
}

/** `config/set` writes an empty string as "delete this key". */
const DELETE_SENTINEL = "";

/**
 * The shape of GET /config/file that this page reads. Deliberately loose: the
 * endpoint returns the whole YAML document, and only these branches matter here.
 */
type ConfigFile = {
  record?: Record<string, unknown>;
  cameras?: Record<string, { record?: Record<string, unknown> } | undefined>;
};

export default function RecordingSettingsView({
  selectedCamera,
  setUnsavedChanges,
}: RecordingSettingsViewProps) {
  const { t } = useTranslation(["views/settings"]);
  const { addMessage, removeMessage } = useContext(StatusBarMessagesContext)!;

  // The merged, running config -- what each camera is actually doing right now.
  const { data: config, mutate: updateConfig } =
    useSWR<Rasid360Config>("config");

  // The config *file*. Needed because the merged view above cannot distinguish
  // "the camera sets this" from "the camera inherits the global value", and an
  // override editor has to know the difference.
  const { data: fileConfig, mutate: updateFileConfig } =
    useSWR<ConfigFile>("config/file");

  const cameraName = useCameraFriendlyName(selectedCamera);
  const [saving, setSaving] = useState(false);

  const cameraNames = useMemo(
    () => Object.keys(config?.cameras ?? {}),
    [config],
  );

  // ---- global state ----------------------------------------------------

  const globalFile = useMemo(() => fileConfig?.record ?? {}, [fileConfig]);

  const globalFromFile = useCallback(
    (path: FieldPath): string => {
      const v = readPath(globalFile, path);
      return v === undefined || v === null ? SCHEMA_DEFAULTS[path] : String(v);
    },
    [globalFile],
  );

  const [globalEnabled, setGlobalEnabled] = useState(true);
  const [globalValues, setGlobalValues] = useState<Record<string, string>>({});

  // ---- per-camera override state ---------------------------------------

  const cameraFile = useMemo(
    () => fileConfig?.cameras?.[selectedCamera]?.record ?? {},
    [fileConfig, selectedCamera],
  );

  // `undefined` in this map means "inherit" -- the key is absent from the file.
  const [overrides, setOverrides] = useState<
    Record<string, string | undefined>
  >({});
  const [enabledOverride, setEnabledOverride] = useState<boolean | undefined>(
    undefined,
  );

  const resetFromFile = useCallback(() => {
    if (!fileConfig) return;

    setGlobalEnabled(Boolean(globalFile?.enabled ?? false));
    setGlobalValues(
      Object.fromEntries(FIELDS.map((f) => [f.path, globalFromFile(f.path)])),
    );
    setOverrides(
      Object.fromEntries(
        FIELDS.map((f) => {
          const v = readPath(cameraFile, f.path);
          return [
            f.path,
            v === undefined || v === null ? undefined : String(v),
          ];
        }),
      ),
    );
    setEnabledOverride(
      cameraFile?.enabled === undefined ? undefined : !!cameraFile.enabled,
    );
    setUnsavedChanges(false);
    removeMessage("recording_settings", "recording_settings");
  }, [
    fileConfig,
    globalFile,
    cameraFile,
    globalFromFile,
    setUnsavedChanges,
    removeMessage,
  ]);

  useEffect(() => {
    resetFromFile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileConfig, selectedCamera]);

  useEffect(() => {
    document.title = t("recording.documentTitle");
  }, [t]);

  const markDirty = useCallback(() => {
    setUnsavedChanges(true);
    addMessage(
      "recording_settings",
      t("recording.unsavedChanges"),
      undefined,
      "recording_settings",
    );
  }, [addMessage, setUnsavedChanges, t]);

  // ---- effective values -------------------------------------------------

  // What this camera will actually use once saved: its override if it has one,
  // otherwise the global value.
  const effective = useCallback(
    (path: FieldPath) => overrides[path] ?? globalValues[path] ?? "",
    [overrides, globalValues],
  );

  const effectiveEnabled = enabledOverride ?? globalEnabled;

  // ---- saving -----------------------------------------------------------

  const coerce = useCallback((path: FieldPath, raw: string) => {
    const field = FIELDS.find((f) => f.path === path)!;
    if (field.kind === "mode") return raw;
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0;
  }, []);

  const save = useCallback(async () => {
    setSaving(true);

    // Only send what actually changed. Writing every field on every save adds
    // keys the config never had, and ruamel re-flows the comments around them --
    // the config file is still hand-edited here, so churn is a real cost.
    const updates: Record<string, unknown> = {};

    if (Boolean(globalFile?.enabled ?? false) !== globalEnabled) {
      updates["record.enabled"] = globalEnabled;
    }

    for (const f of FIELDS) {
      const inFile = readPath(globalFile, f.path);
      const next = coerce(f.path, globalValues[f.path]);

      if (inFile === undefined || inFile === null) {
        // absent from the file: only write it if it differs from the schema
        // default, otherwise writing it changes nothing but the file
        if (String(next) !== SCHEMA_DEFAULTS[f.path]) {
          updates[`record.${f.path}`] = next;
        }
      } else if (String(inFile) !== String(next)) {
        updates[`record.${f.path}`] = next;
      }
    }

    const camPrefix = `cameras.${selectedCamera}.record`;
    const enabledInFile =
      cameraFile?.enabled === undefined ? undefined : !!cameraFile.enabled;

    if (enabledOverride !== enabledInFile) {
      updates[`${camPrefix}.enabled`] =
        enabledOverride === undefined ? DELETE_SENTINEL : enabledOverride;
    }

    for (const f of FIELDS) {
      const raw = readPath(cameraFile, f.path);
      const inFile =
        raw === undefined || raw === null ? undefined : String(raw);
      const next = overrides[f.path];

      if (next === undefined && inFile !== undefined) {
        // override removed -> delete the key so the camera inherits again
        updates[`${camPrefix}.${f.path}`] = DELETE_SENTINEL;
      } else if (next !== undefined && next !== inFile) {
        updates[`${camPrefix}.${f.path}`] = coerce(f.path, next);
      }
    }

    if (Object.keys(updates).length === 0) {
      toast.success(t("recording.toast.noChanges"), { position: "top-center" });
      setUnsavedChanges(false);
      removeMessage("recording_settings", "recording_settings");
      setSaving(false);
      return;
    }

    // A global change is merged down into every camera, and the recording
    // maintainer subscribes per camera -- so publish to all of them, otherwise
    // the change would not apply until a restart.
    const updateTopics = cameraNames.map((c) => `config/cameras/${c}/record`);

    try {
      const response = await axios.put("config/set", {
        config_data: updates,
        requires_restart: 0,
        update_topics: updateTopics,
      });

      if (response.status === 200 && response.data.success !== false) {
        toast.success(t("recording.toast.success"), { position: "top-center" });
        setUnsavedChanges(false);
        removeMessage("recording_settings", "recording_settings");
        updateConfig();
        updateFileConfig();
      } else {
        toast.error(response.data.message ?? t("recording.toast.error"), {
          position: "top-center",
        });
      }
    } catch (error) {
      const message =
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (error as any)?.response?.data?.message ?? t("recording.toast.error");
      toast.error(message, { position: "top-center" });
    } finally {
      setSaving(false);
    }
  }, [
    globalEnabled,
    globalValues,
    globalFile,
    cameraFile,
    overrides,
    enabledOverride,
    selectedCamera,
    cameraNames,
    coerce,
    t,
    setUnsavedChanges,
    removeMessage,
    updateConfig,
    updateFileConfig,
  ]);

  const applyPreset = useCallback(
    (name: keyof typeof PRESETS) => {
      setGlobalValues((prev) => ({ ...prev, ...PRESETS[name] }));
      setGlobalEnabled(true);
      markDirty();
    },
    [markDirty],
  );

  if (!config || !fileConfig) {
    return <ActivityIndicator />;
  }

  // ---- field renderers ---------------------------------------------------

  const renderControl = (
    path: FieldPath,
    value: string,
    onChange: (v: string) => void,
    disabled: boolean,
  ) => {
    const field = FIELDS.find((f) => f.path === path)!;

    if (field.kind === "mode") {
      return (
        <Select
          value={value}
          disabled={disabled}
          onValueChange={(v) => onChange(v)}
        >
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RETAIN_MODES.map((m) => (
              <SelectItem key={m} value={m}>
                {t(`recording.mode.${m}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    return (
      <Input
        type="number"
        min={0}
        step={field.kind === "days" ? 0.5 : 1}
        className="w-40"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  };

  const GlobalField = ({ path }: { path: FieldPath }) => (
    <div className="flex flex-col gap-1.5 py-2 md:flex-row md:items-center md:justify-between">
      <div className="max-w-xl">
        <Label className="text-primary">{t(`recording.field.${path}`)}</Label>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {t(`recording.fieldDesc.${path}`)}
        </p>
      </div>
      {renderControl(
        path,
        globalValues[path] ?? "",
        (v) => {
          setGlobalValues((prev) => ({ ...prev, [path]: v }));
          markDirty();
        },
        false,
      )}
    </div>
  );

  const CameraField = ({ path }: { path: FieldPath }) => {
    const isOverridden = overrides[path] !== undefined;

    return (
      <div className="flex flex-col gap-1.5 py-2 md:flex-row md:items-center md:justify-between">
        <div className="max-w-xl">
          <Label className="text-primary">{t(`recording.field.${path}`)}</Label>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {isOverridden
              ? t("recording.overridden")
              : t("recording.inheriting", {
                  value: globalValues[path],
                })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {renderControl(
            path,
            effective(path),
            (v) => {
              setOverrides((prev) => ({ ...prev, [path]: v }));
              markDirty();
            },
            !isOverridden,
          )}
          <Button
            size="sm"
            variant={isOverridden ? "secondary" : "ghost"}
            aria-pressed={isOverridden}
            onClick={() => {
              setOverrides((prev) => ({
                ...prev,
                [path]: isOverridden ? undefined : globalValues[path],
              }));
              markDirty();
            }}
          >
            {isOverridden ? t("recording.useGlobal") : t("recording.override")}
          </Button>
        </div>
      </div>
    );
  };

  const groupFields = (group: string) =>
    FIELDS.filter((f) => f.group === group).map((f) => f.path);

  return (
    <div className="flex size-full flex-col md:flex-row">
      <Toaster position="top-center" closeButton={true} />
      <div className="scrollbar-container order-last mb-10 mt-2 flex h-full w-full flex-col overflow-y-auto pb-2 md:order-none">
        <Heading as="h3" className="mb-2">
          {t("recording.title")}
        </Heading>
        <p className="mb-4 max-w-4xl text-sm text-muted-foreground">
          {t("recording.desc")}
        </p>

        {/* Capture master switch ------------------------------------------ */}

        <div
          className={cn(
            "mb-4 max-w-4xl rounded-lg border p-4",
            !effectiveEnabled && "border-destructive/50 bg-destructive/5",
          )}
        >
          <div className="flex flex-row items-center gap-3">
            <Switch
              id="record-enabled"
              checked={globalEnabled}
              onCheckedChange={(v) => {
                setGlobalEnabled(v);
                markDirty();
              }}
            />
            <Label htmlFor="record-enabled" className="text-primary">
              {t("recording.capture.label")}
            </Label>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("recording.capture.desc")}
          </p>
          {!effectiveEnabled && (
            <p className="mt-2 flex items-start gap-2 text-sm text-danger">
              <LuInfo className="mt-0.5 size-4 shrink-0" />
              {t("recording.capture.warning")}
            </p>
          )}
        </div>

        {/* Presets -------------------------------------------------------- */}

        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {t("recording.presets.label")}
          </span>
          {(Object.keys(PRESETS) as Array<keyof typeof PRESETS>).map((name) => (
            <Button
              key={name}
              size="sm"
              variant="secondary"
              onClick={() => applyPreset(name)}
            >
              {t(`recording.presets.${name}`)}
            </Button>
          ))}
        </div>

        <Separator className="my-4 bg-secondary" />

        {/* Global defaults ------------------------------------------------ */}

        <Heading as="h4" className="my-2">
          {t("recording.global.title")}
        </Heading>
        <p className="mb-2 max-w-4xl text-sm text-muted-foreground">
          {t("recording.global.desc")}
        </p>

        <div className="max-w-4xl divide-y divide-secondary">
          <div className="py-2">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.storage")}
            </p>
          </div>
          {groupFields("storage").map((p) => (
            <GlobalField key={p} path={p} />
          ))}

          <div className="py-2 pt-4">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.alerts")}
            </p>
            <p className="text-sm text-muted-foreground">
              {t("recording.group.alertsDesc")}
            </p>
          </div>
          {groupFields("alerts").map((p) => (
            <GlobalField key={p} path={p} />
          ))}

          <div className="py-2 pt-4">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.detections")}
            </p>
          </div>
          {groupFields("detections").map((p) => (
            <GlobalField key={p} path={p} />
          ))}
        </div>

        <Separator className="my-6 bg-secondary" />

        {/* Per-camera overrides ------------------------------------------- */}

        <Heading as="h4" className="my-2">
          {t("recording.camera.title", { camera: cameraName })}
        </Heading>
        <p className="mb-2 max-w-4xl text-sm text-muted-foreground">
          {t("recording.camera.desc")}
        </p>

        <div className="max-w-4xl divide-y divide-secondary">
          <div className="flex flex-col gap-1.5 py-2 md:flex-row md:items-center md:justify-between">
            <div className="max-w-xl">
              <Label className="text-primary">
                {t("recording.capture.label")}
              </Label>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {enabledOverride === undefined
                  ? t("recording.inheriting", {
                      value: globalEnabled
                        ? t("recording.on")
                        : t("recording.off"),
                    })
                  : t("recording.overridden")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={effectiveEnabled}
                disabled={enabledOverride === undefined}
                onCheckedChange={(v) => {
                  setEnabledOverride(v);
                  markDirty();
                }}
              />
              <Button
                size="sm"
                variant={enabledOverride === undefined ? "ghost" : "secondary"}
                onClick={() => {
                  setEnabledOverride(
                    enabledOverride === undefined ? globalEnabled : undefined,
                  );
                  markDirty();
                }}
              >
                {enabledOverride === undefined
                  ? t("recording.override")
                  : t("recording.useGlobal")}
              </Button>
            </div>
          </div>

          {FIELDS.map((f) => (
            <CameraField key={f.path} path={f.path} />
          ))}
        </div>

        <div className="mt-6 flex max-w-4xl flex-row gap-2">
          <Button
            className="flex flex-1"
            variant="secondary"
            onClick={resetFromFile}
            disabled={saving}
          >
            {t("button.reset", { ns: "common" })}
          </Button>
          <Button
            className="flex flex-1"
            variant="select"
            onClick={save}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator />
            ) : (
              t("button.save", { ns: "common" })
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
