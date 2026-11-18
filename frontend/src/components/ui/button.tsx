import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';
const buttonVariants = cva('inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 disabled:cursor-not-allowed', { variants: { variant: { default: 'bg-primary text-white hover:opacity-90', outline: 'border border-current bg-transparent' } }, defaultVariants: { variant: 'default' } });
type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { asChild?: boolean };
export function Button({ className, variant, asChild, ...props }: Props) { const Comp = asChild ? Slot : 'button'; return <Comp className={cn(buttonVariants({ variant }), className)} {...props} />; }
