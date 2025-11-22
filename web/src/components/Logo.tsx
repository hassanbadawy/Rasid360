import { cn } from "@/lib/utils";
import logoPng from "../../images/favicon.png";

type LogoProps = {
  className?: string;
};
export default function Logo({ className }: LogoProps) {
  return (
    <img
      src={logoPng}
      alt="Rasid360 Logo"
      className={cn(className)}
    />
  );
}
