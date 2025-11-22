import Heading from "@/components/ui/heading";
import { Label } from "@/components/ui/label";
import { useCallback, useContext, useEffect, useState } from "react";
import { Toaster } from "sonner";
import { Separator } from "../../components/ui/separator";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import { toast } from "sonner";
import useSWR from "swr";
import axios from "axios";
import { Rasid360Config } from "@/types/rasid360Config";
import { CheckCircle2, XCircle } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";
import { IoIosWarning } from "react-icons/io";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { LuExternalLink } from "react-icons/lu";
import { StatusBarMessagesContext } from "@/context/statusbar-provider";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { useDocDomain } from "@/hooks/use-doc-domain";
import { CameraNameLabel } from "@/components/camera/FriendlyNameLabel";

type Rasid360PlusModel = {
  id: string;
  type: string;
  name: string;
  isBaseModel: boolean;
  supportedDetectors: string[];
  trainDate: string;
  baseModel: string;
  width: number;
  height: number;
};

type Rasid360PlusSettings = {
  model: {
    id?: string;
  };
};

type Rasid360SettingsViewProps = {
  setUnsavedChanges: React.Dispatch<React.SetStateAction<boolean>>;
};

export default function Rasid360PlusSettingsView({
  setUnsavedChanges,
}: Rasid360SettingsViewProps) {
  const { t } = useTranslation("views/settings");
  const { getLocaleDocUrl } = useDocDomain();
  const { data: config, mutate: updateConfig } =
    useSWR<Rasid360Config>("config");
  const [changedValue, setChangedValue] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { addMessage, removeMessage } = useContext(StatusBarMessagesContext)!;

  const [rasid360PlusSettings, setRasid360PlusSettings] =
    useState<Rasid360PlusSettings>({
      model: {
        id: undefined,
      },
    });

  const [origPlusSettings, setOrigPlusSettings] = useState<Rasid360PlusSettings>(
    {
      model: {
        id: undefined,
      },
    },
  );

  const { data: availableModels = {} } = useSWR<
    Record<string, Rasid360PlusModel>
  >("/plus/models", {
    fallbackData: {},
    fetcher: async (url) => {
      const res = await axios.get(url, { withCredentials: true });
      return res.data.reduce(
        (obj: Record<string, Rasid360PlusModel>, model: Rasid360PlusModel) => {
          obj[model.id] = model;
          return obj;
        },
        {},
      );
    },
  });

  useEffect(() => {
    if (config) {
      if (rasid360PlusSettings?.model.id == undefined) {
        setRasid360PlusSettings({
          model: {
            id: config.model.plus?.id,
          },
        });
      }

      setOrigPlusSettings({
        model: {
          id: config.model.plus?.id,
        },
      });
    }
    // we know that these deps are correct
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const handleRasid360PlusConfigChange = (
    newConfig: Partial<Rasid360PlusSettings>,
  ) => {
    setRasid360PlusSettings((prevConfig) => ({
      model: {
        ...prevConfig.model,
        ...newConfig.model,
      },
    }));
    setUnsavedChanges(true);
    setChangedValue(true);
  };

  const saveToConfig = useCallback(async () => {
    setIsLoading(true);

    axios
      .put(`config/set?model.path=plus://${rasid360PlusSettings.model.id}`, {
        requires_restart: 0,
      })
      .then((res) => {
        if (res.status === 200) {
          toast.success(t("rasid360Plus.toast.success"), {
            position: "top-center",
          });
          setChangedValue(false);
          updateConfig();
        } else {
          toast.error(
            t("rasid360Plus.toast.error", { errorMessage: res.statusText }),
            {
              position: "top-center",
            },
          );
        }
      })
      .catch((error) => {
        const errorMessage =
          error.response?.data?.message ||
          error.response?.data?.detail ||
          "Unknown error";
        toast.error(
          t("toast.save.error.title", { errorMessage, ns: "common" }),
          {
            position: "top-center",
          },
        );
      })
      .finally(() => {
        addMessage(
          "plus_restart",
          t("rasid360Plus.restart_required"),
          undefined,
          "plus_restart",
        );
        setIsLoading(false);
      });
  }, [updateConfig, addMessage, rasid360PlusSettings, t]);

  const onCancel = useCallback(() => {
    setRasid360PlusSettings(origPlusSettings);
    setChangedValue(false);
    removeMessage("plus_settings", "plus_settings");
  }, [origPlusSettings, removeMessage]);

  useEffect(() => {
    if (changedValue) {
      addMessage(
        "plus_settings",
        t("rasid360Plus.unsavedChanges"),
        undefined,
        "plus_settings",
      );
    } else {
      removeMessage("plus_settings", "plus_settings");
    }
    // we know that these deps are correct
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changedValue]);

  useEffect(() => {
    document.title = t("documentTitle.rasid360Plus");
  }, [t]);

  const needCleanSnapshots = () => {
    if (!config) {
      return false;
    }
    return Object.values(config.cameras).some(
      (camera) => camera.snapshots.enabled && !camera.snapshots.clean_copy,
    );
  };

  if (!config) {
    return <ActivityIndicator />;
  }

  return (
    <>
      <div className="flex size-full flex-col md:flex-row">
        <Toaster position="top-center" closeButton={true} />
        <div className="scrollbar-container order-last mb-10 mt-2 flex h-full w-full flex-col overflow-y-auto pb-2 md:order-none">
          <Heading as="h4" className="mb-2">
            {t("rasid360Plus.title")}
          </Heading>

          <Separator className="my-2 flex bg-secondary" />

          <Heading as="h4" className="my-2">
            {t("rasid360Plus.apiKey.title")}
          </Heading>

          <div className="mt-2 space-y-6">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                {config?.plus?.enabled ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500" />
                )}
                <Label>
                  {config?.plus?.enabled
                    ? t("rasid360Plus.apiKey.validated")
                    : t("rasid360Plus.apiKey.notValidated")}
                </Label>
              </div>
              <div className="my-2 max-w-5xl text-sm text-muted-foreground">
                <p>{t("rasid360Plus.apiKey.desc")}</p>
                {!config?.model.plus && (
                  <>
                    <div className="mt-2 flex items-center text-primary-variant">
                      <Link
                        to="https://rasid360.video/plus"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline"
                      >
                        {t("rasid360Plus.apiKey.plusLink")}
                        <LuExternalLink className="ml-2 inline-flex size-3" />
                      </Link>
                    </div>
                  </>
                )}
              </div>
            </div>

            {config?.model.plus && (
              <>
                <Separator className="my-2 flex bg-secondary" />
                <div className="mt-2 max-w-2xl">
                  <Heading as="h4" className="my-2">
                    {t("rasid360Plus.modelInfo.title")}
                  </Heading>
                  <div className="mt-2 space-y-3">
                    {!config?.model?.plus && (
                      <p className="text-muted-foreground">
                        {t("rasid360Plus.modelInfo.loading")}
                      </p>
                    )}
                    {config?.model?.plus === null && (
                      <p className="text-danger">
                        {t("rasid360Plus.modelInfo.error")}
                      </p>
                    )}
                    {config?.model?.plus && (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label className="text-muted-foreground">
                            {t("rasid360Plus.modelInfo.baseModel")}
                          </Label>
                          <p>
                            {config.model.plus.baseModel} (
                            {config.model.plus.isBaseModel
                              ? t(
                                  "rasid360Plus.modelInfo.plusModelType.baseModel",
                                )
                              : t(
                                  "rasid360Plus.modelInfo.plusModelType.userModel",
                                )}
                            )
                          </p>
                        </div>
                        <div>
                          <Label className="text-muted-foreground">
                            {t("rasid360Plus.modelInfo.trainDate")}
                          </Label>
                          <p>
                            {new Date(
                              config.model.plus.trainDate,
                            ).toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <Label className="text-muted-foreground">
                            {t("rasid360Plus.modelInfo.modelType")}
                          </Label>
                          <p>
                            {config.model.plus.name} (
                            {config.model.plus.width +
                              "x" +
                              config.model.plus.height}
                            )
                          </p>
                        </div>
                        <div>
                          <Label className="text-muted-foreground">
                            {t("rasid360Plus.modelInfo.supportedDetectors")}
                          </Label>
                          <p>
                            {config.model.plus.supportedDetectors.join(", ")}
                          </p>
                        </div>
                        <div className="col-span-2">
                          <div className="space-y-2">
                            <div className="text-md">
                              {t("rasid360Plus.modelInfo.availableModels")}
                            </div>
                            <div className="space-y-3 text-sm text-muted-foreground">
                              <p>
                                <Trans ns="views/settings">
                                  rasid360Plus.modelInfo.modelSelect
                                </Trans>
                              </p>
                            </div>
                          </div>
                          <Select
                            value={rasid360PlusSettings.model.id}
                            onValueChange={(value) =>
                              handleRasid360PlusConfigChange({
                                model: { id: value as string },
                              })
                            }
                          >
                            {rasid360PlusSettings.model.id &&
                            availableModels?.[rasid360PlusSettings.model.id] ? (
                              <SelectTrigger>
                                {new Date(
                                  availableModels[
                                    rasid360PlusSettings.model.id
                                  ].trainDate,
                                ).toLocaleString() +
                                  " " +
                                  availableModels[rasid360PlusSettings.model.id]
                                    .baseModel +
                                  " (" +
                                  (availableModels[rasid360PlusSettings.model.id]
                                    .isBaseModel
                                    ? t(
                                        "rasid360Plus.modelInfo.plusModelType.baseModel",
                                      )
                                    : t(
                                        "rasid360Plus.modelInfo.plusModelType.userModel",
                                      )) +
                                  ") " +
                                  availableModels[rasid360PlusSettings.model.id]
                                    .name +
                                  " (" +
                                  availableModels[rasid360PlusSettings.model.id]
                                    .width +
                                  "x" +
                                  availableModels[rasid360PlusSettings.model.id]
                                    .height +
                                  ")"}
                              </SelectTrigger>
                            ) : (
                              <SelectTrigger>
                                {t(
                                  "rasid360Plus.modelInfo.loadingAvailableModels",
                                )}
                              </SelectTrigger>
                            )}

                            <SelectContent>
                              <SelectGroup>
                                {Object.entries(availableModels || {}).map(
                                  ([id, model]) => (
                                    <SelectItem
                                      key={id}
                                      className="cursor-pointer"
                                      value={id}
                                      disabled={
                                        !model.supportedDetectors.includes(
                                          Object.values(config.detectors)[0]
                                            .type,
                                        )
                                      }
                                    >
                                      {new Date(
                                        model.trainDate,
                                      ).toLocaleString()}{" "}
                                      <div>
                                        {model.baseModel} {" ("}
                                        {model.isBaseModel
                                          ? t(
                                              "rasid360Plus.modelInfo.plusModelType.baseModel",
                                            )
                                          : t(
                                              "rasid360Plus.modelInfo.plusModelType.userModel",
                                            )}
                                        {")"}
                                      </div>
                                      <div>
                                        {model.name} (
                                        {model.width + "x" + model.height})
                                      </div>
                                      <div>
                                        {t(
                                          "rasid360Plus.modelInfo.supportedDetectors",
                                        )}
                                        : {model.supportedDetectors.join(", ")}
                                      </div>
                                      <div className="text-xs text-muted-foreground">
                                        {id}
                                      </div>
                                    </SelectItem>
                                  ),
                                )}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            <Separator className="my-2 flex bg-secondary" />

            <div className="mt-2 max-w-5xl">
              <Heading as="h4" className="my-2">
                {t("rasid360Plus.snapshotConfig.title")}
              </Heading>
              <div className="mt-2 space-y-3">
                <div className="my-2 text-sm text-muted-foreground">
                  <p>
                    <Trans ns="views/settings">
                      rasid360Plus.snapshotConfig.desc
                    </Trans>
                  </p>
                  <div className="mt-2 flex items-center text-primary-variant">
                    <Link
                      to={getLocaleDocUrl("plus/faq")}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline"
                    >
                      {t("readTheDocumentation", { ns: "common" })}
                      <LuExternalLink className="ml-2 inline-flex size-3" />
                    </Link>
                  </div>
                </div>
                {config && (
                  <div className="overflow-x-auto">
                    <table className="max-w-2xl text-sm">
                      <thead>
                        <tr className="border-b border-secondary">
                          <th className="px-4 py-2 text-left">
                            {t("rasid360Plus.snapshotConfig.table.camera")}
                          </th>
                          <th className="px-4 py-2 text-center">
                            {t("rasid360Plus.snapshotConfig.table.snapshots")}
                          </th>
                          <th className="px-4 py-2 text-center">
                            <Trans ns="views/settings">
                              rasid360Plus.snapshotConfig.table.cleanCopySnapshots
                            </Trans>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(config.cameras).map(
                          ([name, camera]) => (
                            <tr
                              key={name}
                              className="border-b border-secondary"
                            >
                              <td className="px-4 py-2">
                                <CameraNameLabel camera={name} />
                              </td>
                              <td className="px-4 py-2 text-center">
                                {camera.snapshots.enabled ? (
                                  <CheckCircle2 className="mx-auto size-5 text-green-500" />
                                ) : (
                                  <XCircle className="mx-auto size-5 text-danger" />
                                )}
                              </td>
                              <td className="px-4 py-2 text-center">
                                {camera.snapshots?.enabled &&
                                camera.snapshots?.clean_copy ? (
                                  <CheckCircle2 className="mx-auto size-5 text-green-500" />
                                ) : (
                                  <XCircle className="mx-auto size-5 text-danger" />
                                )}
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
                {needCleanSnapshots() && (
                  <div className="mt-2 max-w-xl rounded-lg border border-secondary-foreground bg-secondary p-4 text-sm text-danger">
                    <div className="flex items-center gap-2">
                      <IoIosWarning className="mr-2 size-5 text-danger" />
                      <div className="max-w-[85%] text-sm">
                        <Trans ns="views/settings">
                          rasid360Plus.snapshotConfig.cleanCopyWarning
                        </Trans>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <Separator className="my-2 flex bg-secondary" />

            <div className="flex w-full flex-row items-center gap-2 pt-2 md:w-[25%]">
              <Button
                className="flex flex-1"
                aria-label={t("button.reset", { ns: "common" })}
                onClick={onCancel}
              >
                {t("button.reset", { ns: "common" })}
              </Button>
              <Button
                variant="select"
                disabled={!changedValue || isLoading}
                className="flex flex-1"
                aria-label="Save"
                onClick={saveToConfig}
              >
                {isLoading ? (
                  <div className="flex flex-row items-center gap-2">
                    <ActivityIndicator />
                    <span>{t("button.saving", { ns: "common" })}</span>
                  </div>
                ) : (
                  t("button.save", { ns: "common" })
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
