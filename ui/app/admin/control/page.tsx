import { redirect } from 'next/navigation'

/** Control lives in Chat → Control panel. Keep URL for old bookmarks. */
export default function ControlRedirect() {
  redirect('/')
}
