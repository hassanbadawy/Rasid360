import { forwardRef } from "react";
import { LuPlus } from "react-icons/lu";
import Logo from "../Logo";
import { cn } from "@/lib/utils";

type Rasid360PlusIconProps = {
  className?: string;
  onClick?: () => void;
};

const Rasid360PlusIcon = forwardRef<HTMLDivElement, Rasid360PlusIconProps>(
  ({ className, onClick }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("relative flex items-center", className)}
        onClick={onClick}
      >
        <Logo className="size-full" />
        <LuPlus className="absolute size-2 translate-x-3 translate-y-3/4" />
      </div>
    );
  },
);

export default Rasid360PlusIcon;
