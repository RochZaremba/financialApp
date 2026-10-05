"use client";
import {
  useId,
  type ReactNode,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
} from "react";
import {
  ArrowRight,
  AlertCircle,
  Check,
  House,
  ShoppingBasket,
  Zap,
  Car,
  Coffee,
  ShoppingBag,
  Flag,
  ShieldCheck,
  Sun,
  Wallet,
  CircleHelp,
  ReceiptText,
  Landmark,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { money } from "@/lib/money";
export const icons: Record<string, LucideIcon> = {
  house: House,
  basket: ShoppingBasket,
  zap: Zap,
  car: Car,
  coffee: Coffee,
  shopping: ShoppingBag,
  flag: Flag,
  shield: ShieldCheck,
  sun: Sun,
  pocket: Wallet,
  receipt: ReceiptText,
  account: Landmark,
};
export function Icon({
  name,
  color = "green",
  size = 20,
}: {
  name: string;
  color?: string;
  size?: number;
}) {
  const Component = icons[name] || CircleHelp;
  return (
    <span className={`icon-box ${color}`}>
      <Component size={size} strokeWidth={1.7} />
    </span>
  );
}
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}
export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        aria-label={label}
        aria-describedby={hint ? `${id}-hint` : undefined}
        {...props}
      />
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </label>
  );
}
export function MoneyField(
  props: InputHTMLAttributes<HTMLInputElement> & {
    label: string;
    hint?: string;
  },
) {
  return (
    <Field inputMode="decimal" placeholder="0,00" maxLength={14} {...props} />
  );
}
export function Select({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <select id={id} aria-label={label} {...props}>
        {children}
      </select>
    </label>
  );
}
export function ErrorMessage({ error }: { error: string }) {
  return error ? (
    <div className="notice danger" role="alert">
      <AlertCircle size={18} />
      <span>{error}</span>
    </div>
  ) : null;
}
export function Progress({
  value,
  total,
  color = "green",
}: {
  value: number;
  total: number;
  color?: string;
}) {
  const percent =
    total > 0
      ? Math.min(100, Math.max(0, (value / total) * 100))
      : value > 0
        ? 100
        : 0;
  return (
    <div
      className={`progress ${value > total ? "red" : color}`}
      role="progressbar"
      aria-label="Wykorzystanie planu"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}
export function Empty({
  icon = "receipt",
  title,
  description,
  action,
  href,
}: {
  icon?: string;
  title: string;
  description: string;
  action?: string;
  href?: string;
}) {
  return (
    <div className="empty">
      <Icon name={icon} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action && href && (
        <Link className="button primary" href={href}>
          {action}
          <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}
export function SectionTitle({
  title,
  href,
  action = "Zobacz wszystkie",
}: {
  title: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      {href && (
        <Link href={href}>
          {action}
          <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}
export function Amount({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  return <span className={`amount ${className}`}>{money(value)}</span>;
}
export function Submit({
  busy,
  children = "Zapisz",
}: {
  busy: boolean;
  children?: ReactNode;
}) {
  return (
    <button type="submit" className="button primary" disabled={busy}>
      {busy ? (
        <>
          <span className="spinner" />
          Zapisuję…
        </>
      ) : (
        <>
          <Check size={17} />
          {children}
        </>
      )}
    </button>
  );
}
export function Skeleton() {
  return (
    <div
      className="skeleton-layout"
      aria-label="Wczytywanie danych"
      role="status"
    >
      <div className="skeleton heading" />
      <div className="skeleton hero" />
      <div className="two-columns">
        <div className="skeleton panel" />
        <div className="skeleton panel" />
      </div>
      <span className="sr-only">Wczytuję…</span>
    </div>
  );
}
