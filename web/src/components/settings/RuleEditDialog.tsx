import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { ViolationRule, ViolationRuleType } from "@/types/violation";

type RuleEditDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // undefined when creating a new rule
  rule?: ViolationRule;
  camera: string;
  zones: string[];
  trackedObjects: string[];
  existingNames: string[];
  onSave: (rule: ViolationRule) => void;
};

const RULE_TYPES: {
  value: ViolationRuleType;
  label: string;
  hint: string;
}[] = [
  {
    value: "zone_object",
    label: "Object in a zone",
    hint: "Fires as soon as one of the chosen objects is inside the zone.",
  },
  {
    value: "sustained_condition",
    label: "Object in a zone for a while",
    hint: "Fires once the object has stayed in the zone for the monitor duration.",
  },
  {
    value: "zone_sequence",
    label: "Movement between zones",
    hint: "Fires when an object travels from one of the origin zones into the destination zone. Used for wrong-way detection.",
  },
  {
    value: "fall_down",
    label: "Person fallen",
    hint: "Fires when a person's bounding box becomes wider than it is tall.",
  },
];

/** Zone-and-objects rules always take the same condition shape, so the form
 *  builds it rather than asking for DSL. */
function buildCondition(zone: string, objects: string[]): string {
  if (!zone || objects.length === 0) return "";
  const detected = objects.map((o) => `detected(${o})`);
  const objectPart =
    detected.length === 1 ? detected[0] : `(${detected.join(" OR ")})`;
  return `in_zone(${zone}) AND ${objectPart}`;
}

/** Recover {zone, objects} from a condition so an existing rule opens in the
 *  form rather than dropping the user into advanced mode. */
function parseCondition(condition?: string): {
  zone: string;
  objects: string[];
  simple: boolean;
} {
  if (!condition) return { zone: "", objects: [], simple: true };

  const zoneMatch = condition.match(/in_zone\(([^)]+)\)/);
  const objectMatches = [...condition.matchAll(/detected\(([^),]+)\)/g)].map(
    (m) => m[1].trim(),
  );
  const zone = zoneMatch?.[1]?.trim() ?? "";

  // Only treat it as simple if rebuilding reproduces the original.
  const simple =
    !!zone &&
    objectMatches.length > 0 &&
    buildCondition(zone, objectMatches).replace(/\s+/g, "") ===
      condition.replace(/\s+/g, "");

  return { zone, objects: objectMatches, simple };
}

export default function RuleEditDialog({
  open,
  onOpenChange,
  rule,
  camera,
  zones,
  trackedObjects,
  existingNames,
  onSave,
}: RuleEditDialogProps) {
  const { t } = useTranslation(["views/settings"]);
  const isNew = !rule;

  const [name, setName] = useState("");
  const [type, setType] = useState<ViolationRuleType>("zone_object");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);

  // condition builder
  const [zone, setZone] = useState("");
  const [objects, setObjects] = useState<string[]>([]);
  const [advanced, setAdvanced] = useState(false);
  const [rawCondition, setRawCondition] = useState("");

  // zone_sequence
  const [fromZones, setFromZones] = useState<string[]>([]);
  const [toZone, setToZone] = useState("");
  const [vehicleTypes, setVehicleTypes] = useState<string[]>([]);
  const [minDetections, setMinDetections] = useState(1);

  // fall_down
  const [widthHeightRatio, setWidthHeightRatio] = useState(1.2);
  const [minDuration, setMinDuration] = useState(3);

  // timing
  const [monitorDuration, setMonitorDuration] = useState(10);
  const [cooldown, setCooldown] = useState(30);
  const [severity, setSeverity] = useState("medium");
  const [duration, setDuration] = useState(30);
  const [speedThreshold, setSpeedThreshold] = useState<number | undefined>();

  // Reset the form whenever the dialog opens on a different rule.
  useEffect(() => {
    if (!open) return;

    setName(rule?.name ?? "");
    setType(rule?.type ?? "zone_object");
    setDescription(rule?.description ?? "");
    setEnabled(rule?.enabled ?? true);

    const parsed = parseCondition(rule?.condition);
    setZone(parsed.zone);
    setObjects(parsed.objects);
    setAdvanced(!!rule?.condition && !parsed.simple);
    setRawCondition(rule?.condition ?? "");

    setFromZones(rule?.from_zones ?? []);
    setToZone(rule?.to_zone ?? "");
    setVehicleTypes(rule?.vehicle_types ?? []);
    setMinDetections(rule?.min_detections ?? 1);

    setWidthHeightRatio(rule?.width_height_ratio ?? 1.2);
    setMinDuration(Number(rule?.min_duration ?? 3));

    setMonitorDuration(rule?.monitor_duration ?? 10);
    setCooldown(rule?.cooldown ?? 30);
    setSeverity(rule?.severity ?? "medium");
    setDuration(rule?.duration ?? 30);
    setSpeedThreshold(rule?.speed_threshold);
  }, [open, rule]);

  const condition = advanced ? rawCondition : buildCondition(zone, objects);
  const usesCondition =
    type === "zone_object" || type === "sustained_condition";

  const nameError = useMemo(() => {
    if (!name.trim()) return "A name is required.";
    if (!/^[A-Za-z0-9_]+$/.test(name))
      return "Use letters, numbers and underscores only.";
    if (existingNames.includes(name) && name !== rule?.name)
      return "Another rule on this camera already uses that name.";
    return undefined;
  }, [name, existingNames, rule?.name]);

  const formError = useMemo(() => {
    if (nameError) return nameError;
    if (usesCondition && !condition)
      return "Choose a zone and at least one object.";
    if (type === "zone_sequence") {
      if (fromZones.length === 0) return "Choose at least one origin zone.";
      if (!toZone) return "Choose a destination zone.";
      if (vehicleTypes.length === 0) return "Choose at least one object.";
    }
    return undefined;
  }, [
    nameError,
    usesCondition,
    condition,
    type,
    fromZones,
    toZone,
    vehicleTypes,
  ]);

  const toggle = useCallback(
    (list: string[], value: string, set: (v: string[]) => void) => {
      set(
        list.includes(value)
          ? list.filter((v) => v !== value)
          : [...list, value],
      );
    },
    [],
  );

  const handleSave = useCallback(() => {
    if (formError) return;

    // Only send fields that apply to the chosen type -- the config model
    // forbids unknown keys and validates required ones per type.
    const next: ViolationRule = {
      name: name.trim(),
      enabled,
      type,
      description: description.trim(),
      duration,
      severity,
      cooldown,
    };

    if (usesCondition) next.condition = condition;
    if (type === "sustained_condition") {
      next.monitor_duration = monitorDuration;
      if (speedThreshold) next.speed_threshold = speedThreshold;
    }
    if (type === "zone_sequence") {
      next.from_zones = fromZones;
      next.to_zone = toZone;
      next.vehicle_types = vehicleTypes;
      next.min_detections = minDetections;
    }
    if (type === "fall_down") {
      next.object_type = "person";
      next.width_height_ratio = widthHeightRatio;
      next.min_duration = minDuration;
    }

    onSave(next);
    onOpenChange(false);
  }, [
    formError,
    name,
    enabled,
    type,
    description,
    duration,
    severity,
    cooldown,
    usesCondition,
    condition,
    monitorDuration,
    speedThreshold,
    fromZones,
    toZone,
    vehicleTypes,
    minDetections,
    widthHeightRatio,
    minDuration,
    onSave,
    onOpenChange,
  ]);

  const selectedType = RULE_TYPES.find((rt) => rt.value === type);

  const ChipList = ({
    options,
    selected,
    onToggle,
    empty,
  }: {
    options: string[];
    selected: string[];
    onToggle: (value: string) => void;
    empty: string;
  }) =>
    options.length === 0 ? (
      <div className="text-sm text-danger">{empty}</div>
    ) : (
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Button
            key={option}
            type="button"
            size="sm"
            variant={selected.includes(option) ? "select" : "default"}
            onClick={() => onToggle(option)}
          >
            {option}
          </Button>
        ))}
      </div>
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isNew ? t("rules.dialog.add") : t("rules.dialog.edit")}
          </DialogTitle>
          <DialogDescription>
            {t("rules.dialog.desc", { camera })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="rule-name">{t("rules.field.name")}</Label>
            <Input
              id="rule-name"
              value={name}
              placeholder="no_parking_violation"
              onChange={(e) => setName(e.target.value)}
            />
            <div className="text-xs text-primary/60">
              {t("rules.field.nameHint")}
            </div>
            {nameError && (
              <div className="text-xs text-danger">{nameError}</div>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label>{t("rules.field.type")}</Label>
            <Select
              value={type}
              onValueChange={(v) => setType(v as ViolationRuleType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RULE_TYPES.map((rt) => (
                  <SelectItem key={rt.value} value={rt.value}>
                    {rt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedType && (
              <div className="text-xs text-primary/60">{selectedType.hint}</div>
            )}
          </div>

          <Separator />

          {usesCondition && (
            <>
              <div className="flex items-center justify-between">
                <Label>{t("rules.field.where")}</Label>
                <div className="flex items-center gap-2">
                  <Switch
                    id="advanced"
                    checked={advanced}
                    onCheckedChange={(checked) => {
                      if (checked) setRawCondition(condition);
                      setAdvanced(checked);
                    }}
                  />
                  <Label htmlFor="advanced" className="text-xs">
                    {t("rules.field.advanced")}
                  </Label>
                </div>
              </div>

              {advanced ? (
                <Textarea
                  value={rawCondition}
                  rows={3}
                  className="font-mono text-sm"
                  onChange={(e) => setRawCondition(e.target.value)}
                  placeholder="in_zone(no_parking) AND (detected(car) OR detected(truck))"
                />
              ) : (
                <>
                  <Select value={zone} onValueChange={setZone}>
                    <SelectTrigger>
                      <SelectValue placeholder={t("rules.field.selectZone")} />
                    </SelectTrigger>
                    <SelectContent>
                      {zones.map((z) => (
                        <SelectItem key={z} value={z}>
                          {z}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Label>{t("rules.field.objects")}</Label>
                  <ChipList
                    options={trackedObjects}
                    selected={objects}
                    onToggle={(v) => toggle(objects, v, setObjects)}
                    empty={t("rules.noObjects")}
                  />
                </>
              )}

              {condition && (
                <div className="font-mono rounded-md bg-secondary p-2 text-xs text-primary/70">
                  {condition}
                </div>
              )}
            </>
          )}

          {type === "zone_sequence" && (
            <>
              <Label>{t("rules.field.fromZones")}</Label>
              <ChipList
                options={zones}
                selected={fromZones}
                onToggle={(v) => toggle(fromZones, v, setFromZones)}
                empty={t("rules.noZones")}
              />

              <Label>{t("rules.field.toZone")}</Label>
              <Select value={toZone} onValueChange={setToZone}>
                <SelectTrigger>
                  <SelectValue placeholder={t("rules.field.selectZone")} />
                </SelectTrigger>
                <SelectContent>
                  {zones.map((z) => (
                    <SelectItem key={z} value={z}>
                      {z}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Label>{t("rules.field.objects")}</Label>
              <ChipList
                options={trackedObjects}
                selected={vehicleTypes}
                onToggle={(v) => toggle(vehicleTypes, v, setVehicleTypes)}
                empty={t("rules.noObjects")}
              />

              <div className="flex flex-col gap-2">
                <Label htmlFor="min-det">
                  {t("rules.field.minDetections")}
                </Label>
                <Input
                  id="min-det"
                  type="number"
                  min={1}
                  value={minDetections}
                  onChange={(e) => setMinDetections(Number(e.target.value))}
                />
                <div className="text-xs text-primary/60">
                  {t("rules.field.minDetectionsHint")}
                </div>
              </div>
            </>
          )}

          {type === "fall_down" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="ratio">{t("rules.field.ratio")}</Label>
                <Input
                  id="ratio"
                  type="number"
                  step="0.1"
                  min={0.1}
                  value={widthHeightRatio}
                  onChange={(e) => setWidthHeightRatio(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="min-dur">{t("rules.field.minDuration")}</Label>
                <Input
                  id="min-dur"
                  type="number"
                  min={0}
                  value={minDuration}
                  onChange={(e) => setMinDuration(Number(e.target.value))}
                />
              </div>
            </div>
          )}

          {type === "sustained_condition" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="monitor">
                  {t("rules.field.monitorDuration")}
                </Label>
                <Input
                  id="monitor"
                  type="number"
                  min={1}
                  value={monitorDuration}
                  onChange={(e) => setMonitorDuration(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="speed">{t("rules.field.speed")}</Label>
                <Input
                  id="speed"
                  type="number"
                  min={1}
                  placeholder={t("rules.field.speedPlaceholder")}
                  value={speedThreshold ?? ""}
                  onChange={(e) =>
                    setSpeedThreshold(
                      e.target.value ? Number(e.target.value) : undefined,
                    )
                  }
                />
                <div className="text-xs text-primary/60">
                  {t("rules.field.speedHint")}
                </div>
              </div>
            </div>
          )}

          <Separator />

          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="cooldown">{t("rules.field.cooldown")}</Label>
              <Input
                id="cooldown"
                type="number"
                min={0}
                value={cooldown}
                onChange={(e) => setCooldown(Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="duration">{t("rules.field.duration")}</Label>
              <Input
                id="duration"
                type="number"
                min={1}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>{t("rules.field.severity")}</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["low", "medium", "high", "critical"].map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="desc">{t("rules.field.description")}</Label>
            <Input
              id="desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
            <Label htmlFor="enabled">{t("rules.field.enabled")}</Label>
          </div>
        </div>

        <DialogFooter>
          {formError && (
            <div className="mr-auto self-center text-xs text-danger">
              {formError}
            </div>
          )}
          <Button type="button" onClick={() => onOpenChange(false)}>
            {t("button.cancel", { ns: "common" })}
          </Button>
          <Button
            variant="select"
            type="button"
            disabled={!!formError}
            onClick={handleSave}
          >
            {t("button.save", { ns: "common" })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
