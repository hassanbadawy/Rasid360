export type ViolationRuleType =
  | "object_logic"
  | "zone_object"
  | "zone_sequence"
  | "sustained_condition"
  | "proximity"
  | "fall_down";

/**
 * A violation rule as stored under cameras.<name>.violations in the Frigate
 * config. Mirrors ViolationRuleConfig in frigate/config/camera/violation.py --
 * that model forbids unknown keys, so only send fields that apply to the type.
 */
export type ViolationRule = {
  name: string;
  enabled: boolean;
  type: ViolationRuleType;
  description?: string;

  duration?: number;
  severity?: string;
  cooldown?: number;
  retention_days?: number;

  // zone_object / object_logic / sustained_condition
  condition?: string;

  // sustained_condition
  monitor_duration?: number;
  speed_threshold?: number;

  // zone_sequence
  vehicle_types?: string[];
  from_zones?: string[];
  to_zone?: string;
  min_detections?: number;

  // fall_down
  object_type?: string;
  width_height_ratio?: number;
  min_duration?: number;

  // proximity
  first_object?: string;
  second_object?: string;
  within?: number;
};
