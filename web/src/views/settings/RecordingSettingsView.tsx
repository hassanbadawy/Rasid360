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
 * Every field this page can write.
 *
 * `section` is the top-level config block the path hangs off. Most fields live
 * under `record:`, but the two `review:` switches belong here too: they decide
 * whether a review item is created at all, and a review item is what causes a
 * recording segment to be kept. Retention windows only decide how long. A user
 * can zero every `record:` field on this page and still fill the disk if the
 * `review:` switches are on, which is why they are not on a separate screen.
 *
 * `kind` drives both the control and the coercion applied before the value is
 * sent -- config/set stores whatever JSON it is given, so a number field that
 * submits a string would write `days: "30"` into the YAML and fail validation.
 */
const FIELDS = [
  { path: "alerts.enabled", section: "review", kind: "bool", group: "review" },
  {
    path: "detections.enabled",
    section: "review",
    kind: "bool",
    group: "review",
  },
  {
    path: "continuous.days",
    section: "record",
    kind: "days",
    group: "storage",
  },
  { path: "motion.days", section: "record", kind: "days", group: "storage" },
  {
    path: "alerts.retain.days",
    section: "record",
    kind: "days",
    group: "alerts",
  },
  {
    path: "alerts.retain.mode",
    section: "record",
    kind: "mode",
    group: "alerts",
  },
  {
    path: "alerts.pre_capture",
    section: "record",
    kind: "seconds",
    group: "alerts",
  },
  {
    path: "alerts.post_capture",
    section: "record",
    kind: "seconds",
    group: "alerts",
  },
  {
    path: "detections.retain.days",
    section: "record",
    kind: "days",
    group: "detections",
  },
  {
    path: "detections.retain.mode",
    section: "record",
    kind: "mode",
    group: "detections",
  },
  {
    path: "detections.pre_capture",
    section: "record",
    kind: "seconds",
    group: "detections",
  },
  {
    path: "detections.post_capture",
    section: "record",
    kind: "seconds",
    group: "detections",
  },
] as const;

type Field = (typeof FIELDS)[number];

/** Unique key for a field, since `alerts.enabled` and `alerts.retain.days`
 * would otherwise collide across sections. */
const keyOf = (f: { section: string; path: string }) =>
  `${f.section}.${f.path}`;

const FIELD_BY_KEY = Object.fromEntries(
  FIELDS.map((f) => [keyOf(f), f]),
) as Record<string, Field>;

// Schema defaults from frigate/config/camera/record.py and review.py, used when
// neither the file nor a preset has set a value. Both review switches default
// ON upstream, which is what a fresh install gets.
const SCHEMA_DEFAULTS: Record<string, string> = {
  "review.alerts.enabled": "true",
  "review.detections.enabled": "true",
  "record.continuous.days": "0",
  "record.motion.days": "0",
  "record.alerts.retain.days": "10",
  "record.alerts.retain.mode": "motion",
  "record.alerts.pre_capture": "5",
  "record.alerts.post_capture": "5",
  "record.detections.retain.days": "10",
  "record.detections.retain.mode": "motion",
  "record.detections.pre_capture": "5",
  "record.detections.post_capture": "5",
};

const PRESETS: Record<string, Record<string, string>> = {
  // Only violations are kept. Ordinary review items are off, which is the part
  // that actually bounds storage -- see the note on FIELDS above.
  violationsOnly: {
    "review.alerts.enabled": "false",
    "review.detections.enabled": "false",
    "record.continuous.days": "0",
    "record.motion.days": "0",
    "record.alerts.retain.days": "30",
    "record.alerts.retain.mode": "all",
    "record.detections.retain.days": "0",
  },
  motionBuffer: {
    "review.alerts.enabled": "true",
    "review.detections.enabled": "false",
    "record.continuous.days": "0",
    "record.motion.days": "2",
    "record.alerts.retain.days": "14",
    "record.alerts.retain.mode": "all",
    "record.detections.retain.days": "2",
  },
  everything: {
    "review.alerts.enabled": "true",
    "review.detections.enabled": "true",
    "record.continuous.days": "7",
    "record.motion.days": "14",
    "record.alerts.retain.days": "30",
    "record.alerts.retain.mode": "all",
    "record.detections.retain.days": "30",
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
  review?: Record<string, unknown>;
  cameras?: Record<
    string,
    | {
        record?: Record<string, unknown>;
        review?: Record<string, unknown>;
      }
    | undefined
  >;
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

  const globalFile = useMemo(
    () => ({
      record: fileConfig?.record ?? {},
      review: fileConfig?.review ?? {},
    }),
    [fileConfig],
  );

  const globalFromFile = useCallback(
    (f: Field): string => {
      const v = readPath(globalFile[f.section], f.path);
      return v === undefined || v === null
        ? SCHEMA_DEFAULTS[keyOf(f)]
        : String(v);
    },
    [globalFile],
  );

  const [globalEnabled, setGlobalEnabled] = useState(true);
  const [globalValues, setGlobalValues] = useState<Record<string, string>>({});

  // ---- per-camera override state ---------------------------------------

  const cameraFile = useMemo(
    () => ({
      record: fileConfig?.cameras?.[selectedCamera]?.record ?? {},
      review: fileConfig?.cameras?.[selectedCamera]?.review ?? {},
    }),
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

    setGlobalEnabled(Boolean(globalFile.record?.enabled ?? false));
    setGlobalValues(
      Object.fromEntries(FIELDS.map((f) => [keyOf(f), globalFromFile(f)])),
    );
    setOverrides(
      Object.fromEntries(
        FIELDS.map((f) => {
          const v = readPath(cameraFile[f.section], f.path);
          return [
            keyOf(f),
            v === undefined || v === null ? undefined : String(v),
          ];
        }),
      ),
    );
    setEnabledOverride(
      cameraFile.record?.enabled === undefined
        ? undefined
        : !!cameraFile.record.enabled,
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
    (key: string) => overrides[key] ?? globalValues[key] ?? "",
    [overrides, globalValues],
  );

  const effectiveEnabled = enabledOverride ?? globalEnabled;

  // ---- saving -----------------------------------------------------------

  const coerce = useCallback((key: string, raw: string) => {
    const field = FIELD_BY_KEY[key];
    if (field.kind === "mode") return raw;
    if (field.kind === "bool") return raw === "true";
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0;
  }, []);

  const save = useCallback(async () => {
    setSaving(true);

    // Only send what actually changed. Writing every field on every save adds
    // keys the config never had, and ruamel re-flows the comments around them --
    // the config file is still hand-edited here, so churn is a real cost.
    const updates: Record<string, unknown> = {};

    if (Boolean(globalFile.record?.enabled ?? false) !== globalEnabled) {
      updates["record.enabled"] = globalEnabled;
    }

    for (const f of FIELDS) {
      const key = keyOf(f);
      const inFile = readPath(globalFile[f.section], f.path);
      const next = coerce(key, globalValues[key]);

      if (inFile === undefined || inFile === null) {
        // absent from the file: only write it if it differs from the schema
        // default, otherwise writing it changes nothing but the file
        if (String(next) !== SCHEMA_DEFAULTS[key]) {
          updates[key] = next;
        }
      } else if (String(inFile) !== String(next)) {
        updates[key] = next;
      }
    }

    const camPrefix = `cameras.${selectedCamera}`;
    const enabledInFile =
      cameraFile.record?.enabled === undefined
        ? undefined
        : !!cameraFile.record.enabled;

    if (enabledOverride !== enabledInFile) {
      updates[`${camPrefix}.record.enabled`] =
        enabledOverride === undefined ? DELETE_SENTINEL : enabledOverride;
    }

    for (const f of FIELDS) {
      const key = keyOf(f);
      const raw = readPath(cameraFile[f.section], f.path);
      const inFile =
        raw === undefined || raw === null ? undefined : String(raw);
      const next = overrides[key];

      if (next === undefined && inFile !== undefined) {
        // override removed -> delete the key so the camera inherits again
        updates[`${camPrefix}.${key}`] = DELETE_SENTINEL;
      } else if (next !== undefined && next !== inFile) {
        updates[`${camPrefix}.${key}`] = coerce(key, next);
      }
    }

    if (Object.keys(updates).length === 0) {
      toast.success(t("recording.toast.noChanges"), { position: "top-center" });
      setUnsavedChanges(false);
      removeMessage("recording_settings", "recording_settings");
      setSaving(false);
      return;
    }

    // A global change is merged down into every camera, and the maintainers
    // subscribe per camera -- so publish to all of them, otherwise the change
    // would not apply until a restart. Both topics: RecordingMaintainer listens
    // on `record`, ReviewSegmentMaintainer on `review`.
    const updateTopics = cameraNames.flatMap((c) => [
      `config/cameras/${c}/record`,
      `config/cameras/${c}/review`,
    ]);

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
    key: string,
    value: string,
    onChange: (v: string) => void,
    disabled: boolean,
  ) => {
    const field = FIELD_BY_KEY[key];

    if (field.kind === "bool") {
      return (
        <div className="flex w-40 items-center">
          <Switch
            checked={value === "true"}
            disabled={disabled}
            onCheckedChange={(v) => onChange(v ? "true" : "false")}
          />
        </div>
      );
    }

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

  const GlobalField = ({ fieldKey }: { fieldKey: string }) => (
    <div className="flex flex-col gap-1.5 py-2 md:flex-row md:items-center md:justify-between">
      <div className="max-w-xl">
        <Label className="text-primary">
          {t(`recording.field.${fieldKey}`)}
        </Label>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {t(`recording.fieldDesc.${fieldKey}`)}
        </p>
      </div>
      {renderControl(
        fieldKey,
        globalValues[fieldKey] ?? "",
        (v) => {
          setGlobalValues((prev) => ({ ...prev, [fieldKey]: v }));
          markDirty();
        },
        false,
      )}
    </div>
  );

  const CameraField = ({ fieldKey }: { fieldKey: string }) => {
    const isOverridden = overrides[fieldKey] !== undefined;

    return (
      <div className="flex flex-col gap-1.5 py-2 md:flex-row md:items-center md:justify-between">
        <div className="max-w-xl">
          <Label className="text-primary">
            {t(`recording.field.${fieldKey}`)}
          </Label>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {isOverridden
              ? t("recording.overridden")
              : t("recording.inheriting", {
                  value: globalValues[fieldKey],
                })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {renderControl(
            fieldKey,
            effective(fieldKey),
            (v) => {
              setOverrides((prev) => ({ ...prev, [fieldKey]: v }));
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
                [fieldKey]: isOverridden ? undefined : globalValues[fieldKey],
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
    FIELDS.filter((f) => f.group === group).map((f) => keyOf(f));

  // Ordinary review items on + a long alert window is the combination that
  // silently fills a disk: every person/car pins the footage it overlaps, and
  // on a busy camera those review segments never close.
  const heavyRetention =
    (globalValues["review.alerts.enabled"] === "true" ||
      globalValues["review.detections.enabled"] === "true") &&
    Number(globalValues["record.alerts.retain.days"] ?? 0) > 7;

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
              {t("recording.group.review")}
            </p>
            <p className="text-sm text-muted-foreground">
              {t("recording.group.reviewDesc")}
            </p>
          </div>
          {groupFields("review").map((k) => (
            <GlobalField key={k} fieldKey={k} />
          ))}

          {heavyRetention && (
            <div className="py-3">
              <p className="flex items-start gap-2 text-sm text-danger">
                <LuInfo className="mt-0.5 size-4 shrink-0" />
                {t("recording.group.reviewWarning")}
              </p>
            </div>
          )}

          <div className="py-2 pt-4">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.storage")}
            </p>
          </div>
          {groupFields("storage").map((k) => (
            <GlobalField key={k} fieldKey={k} />
          ))}

          <div className="py-2 pt-4">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.alerts")}
            </p>
            <p className="text-sm text-muted-foreground">
              {t("recording.group.alertsDesc")}
            </p>
          </div>
          {groupFields("alerts").map((k) => (
            <GlobalField key={k} fieldKey={k} />
          ))}

          <div className="py-2 pt-4">
            <p className="text-sm font-medium text-primary">
              {t("recording.group.detections")}
            </p>
          </div>
          {groupFields("detections").map((k) => (
            <GlobalField key={k} fieldKey={k} />
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
            <CameraField key={keyOf(f)} fieldKey={keyOf(f)} />
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
