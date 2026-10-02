import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "btn [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "btn-primary",
        outline: "btn-soft",
        secondary: "btn-soft",
        ghost: "btn-ghost",
        destructive: "btn-danger",
        link: "btn-ghost",
      },
      size: {
        default: "",
        xs: "btn-sm",
        sm: "btn-sm",
        lg: "btn-lg",
        icon: "btn-sm",
        "icon-xs": "btn-sm",
        "icon-sm": "btn-sm",
        "icon-lg": "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
