import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { WorkspaceShell } from './components/shell/WorkspaceShell'
import './globals.css'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] })

export const metadata: Metadata = {
  title: {
    default: 'Mina',
    template: '%s · Mina',
  },
  description:
    'Talk with Mina — a living conversational mind with real-time presence control.',
  applicationName: 'Mina',
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  themeColor: '#0b0b0d',
  width: 'device-width',
  initialScale: 1,
  colorScheme: 'dark',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <WorkspaceShell>{children}</WorkspaceShell>
      </body>
    </html>
  )
}
