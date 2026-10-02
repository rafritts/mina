import { redirect } from 'next/navigation'

/** Retired control URL. Bookmarks land on Chat; tools live in the header sheet. */
export default function ControlRedirect() {
  redirect('/')
}
