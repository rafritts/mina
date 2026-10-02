/** Instrumentation routes share the workspace shell. This frame only scrolls the page. */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className="shell-scroll">{children}</div>
}
