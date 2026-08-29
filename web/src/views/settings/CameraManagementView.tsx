import Heading from "@/components/ui/heading";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Toaster, toast } from "sonner";
import axios from "axios";
import { Button } from "@/components/ui/button";
import useSWR from "swr";
import { Rasid360Config } from "@/types/rasid360Config";
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import CameraEditForm from "@/components/settings/CameraEditForm";
import CameraWizardDialog from "@/components/settings/CameraWizardDialog";
import { LuPlus } from "react-icons/lu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { IoMdArrowRoundBack } from "react-icons/io";
import { isDesktop } from "react-device-detect";
import { CameraNameLabel } from "@/components/camera/FriendlyNameLabel";
import { Switch } from "@/components/ui/switch";
import { Trans } from "react-i18next";
import { Separator } from "@/components/ui/separator";

type CameraManagementViewProps = {
  setUnsavedChanges: React.Dispatch<React.SetStateAction<boolean>>;
};

export default function CameraManagementView({
  setUnsavedChanges,
}: CameraManagementViewProps) {
  const { t } = useTranslation(["views/settings"]);

  const { data: config, mutate: updateConfig } =
    useSWR<Rasid360Config>("config");

  const [viewMode, setViewMode] = useState<"settings" | "add" | "edit">(
    "settings",
  ); // Control view state
  const [editCameraName, setEditCameraName] = useState<string | undefined>(
    undefined,
  ); // Track camera being edited
  const [showWizard, setShowWizard] = useState(false);

  // List of cameras for dropdown
  const cameras = useMemo(() => {
    if (config) {
      return Object.keys(config.cameras).sort();
    }
    return [];
  }, [config]);

  useEffect(() => {
    document.title = t("documentTitle.cameraManagement");
  }, [t]);

  // Handle back navigation from add/edit form
  const handleBack = useCallback(() => {
    setViewMode("settings");
    setEditCameraName(undefined);
    setUnsavedChanges(false);
    updateConfig();
  }, [updateConfig, setUnsavedChanges]);

  return (
    <>
      <Toaster
        richColors
        className="z-[1000]"
        position="top-center"
        closeButton
      />
      <div className="flex size-full flex-col md:flex-row">
        <div className="scrollbar-container order-last mb-10 mt-2 flex h-full w-full flex-col overflow-y-auto pb-2 md:order-none">
          {viewMode === "settings" ? (
            <>
              <Heading as="h4" className="mb-2">
                {t("cameraManagement.title")}
              </Heading>
              <div className="my-4 flex flex-col gap-4">
                <Button
                  variant="select"
                  onClick={() => setShowWizard(true)}
                  className="flex max-w-48 items-center gap-2"
                >
                  <LuPlus className="h-4 w-4" />
                  {t("cameraManagement.addCamera")}
                </Button>
                {cameras.length > 0 && (
                  <>
                    <div className="my-4 flex flex-col gap-2">
                      <Label>{t("cameraManagement.editCamera")}</Label>
                      <Select
                        onValueChange={(value) => {
                          setEditCameraName(value);
                          setViewMode("edit");
                        }}
                      >
                        <SelectTrigger className="w-[180px]">
                          <SelectValue
                            placeholder={t("cameraManagement.selectCamera")}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {cameras.map((camera) => {
                            return (
                              <SelectItem key={camera} value={camera}>
                                <CameraNameLabel camera={camera} />
                              </SelectItem>
                            );
                          })}
                        </SelectContent>
                      </Select>
                    </div>

                    <Separator className="my-2 flex bg-secondary" />
                    <div className="max-w-7xl space-y-4">
                      <Heading as="h4" className="my-2">
                        <Trans ns="views/settings">
                          cameraManagement.streams.title
                        </Trans>
                      </Heading>
                      <div className="mt-3 text-sm text-muted-foreground">
                        <Trans ns="views/settings">
                          cameraManagement.streams.desc
                        </Trans>
                      </div>

                      <div className="max-w-md space-y-2 rounded-lg bg-secondary p-4">
                        {cameras.map((camera) => (
                          <div
                            key={camera}
                            className="flex items-center justify-between smart-capitalize"
                          >
                            <CameraNameLabel camera={camera} />
                            <CameraEnableSwitch cameraName={camera} />
                          </div>
                        ))}
                      </div>
                    </div>
                    <Separator className="mb-2 mt-4 flex bg-secondary" />
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="mb-4 flex items-center gap-2">
                <Button
                  className={`flex items-center gap-2.5 rounded-lg`}
                  aria-label={t("label.back", { ns: "common" })}
                  size="sm"
                  onClick={handleBack}
                >
                  <IoMdArrowRoundBack className="size-5 text-secondary-foreground" />
                  {isDesktop && (
                    <div className="text-primary">
                      {t("button.back", { ns: "common" })}
                    </div>
                  )}
                </Button>
              </div>
              <div className="md:max-w-5xl">
                <CameraEditForm
                  cameraName={viewMode === "edit" ? editCameraName : undefined}
                  onSave={handleBack}
                  onCancel={handleBack}
                />
              </div>
            </>
          )}
        </div>
      </div>

      <CameraWizardDialog
        open={showWizard}
        onClose={() => setShowWizard(false)}
      />
    </>
  );
}

type CameraEnableSwitchProps = {
  cameraName: string;
};

function CameraEnableSwitch({ cameraName }: CameraEnableSwitchProps) {
  // Deliberately NOT driven by the websocket state.
  //
  // `<camera>/enabled/set` can only ever turn a camera *off*: Dispatcher's
  // _on_enabled_command refuses "ON" unless enabled_in_config is true, and
  // returns early without publishing `<camera>/enabled/state`. Once this switch
  // persisted a camera off, enabled_in_config became false on the next restart
  // and the websocket could no longer turn it back on -- the switch would sit
  // there refusing to move.
  //
  // So the switch reflects the config, which is the thing that actually decides
  // whether a camera runs, with an optimistic local value so it responds to the
  // click rather than to a round trip.
  const { data: config, mutate: updateConfig } =
    useSWR<Rasid360Config>("config");
  const configEnabled = config?.cameras?.[cameraName]?.enabled ?? true;

  const [pending, setPending] = useState<boolean | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const { t } = useTranslation(["views/settings"]);

  // Drop the optimistic value once the config agrees with it.
  useEffect(() => {
    if (pending !== undefined && pending === configEnabled) {
      setPending(undefined);
    }
  }, [pending, configEnabled]);

  const enabled = pending ?? configEnabled;

  // `update_topic` is what applies the change without a restart: it publishes
  // the same CameraConfigUpdateEnum.enabled that the websocket path publishes,
  // and the capture and detection processes subscribe to it.
  const toggle = useCallback(
    async (isChecked: boolean) => {
      setPending(isChecked);
      setSaving(true);

      try {
        const response = await axios.put("config/set", {
          config_data: { cameras: { [cameraName]: { enabled: isChecked } } },
          requires_restart: 0,
          update_topic: `config/cameras/${cameraName}/enabled`,
        });

        if (response.status !== 200 || response.data.success === false) {
          setPending(undefined);
          toast.error(
            response.data?.message ?? t("cameraManagement.streams.toast.error"),
            { position: "top-center" },
          );
        } else {
          updateConfig();
        }
      } catch (error) {
        setPending(undefined);
        const message =
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (error as any)?.response?.data?.message ??
          t("cameraManagement.streams.toast.error");
        toast.error(message, { position: "top-center" });
      } finally {
        setSaving(false);
      }
    },
    [cameraName, t, updateConfig],
  );

  return (
    <div className="flex flex-row items-center">
      <Switch
        id={`camera-enabled-${cameraName}`}
        checked={enabled}
        disabled={saving}
        onCheckedChange={toggle}
      />
    </div>
  );
}
