/** Strip image markup so a bubble is never drawn as a picture. */

const MD_IMAGE = /!\[[^\]]*\]\([^)]*\)/g
const HTML_IMAGE = /<img\b[^>]*>/gi
const BARE_HOST_IMAGE = /(?<![\w(/])(?:\/images\/|\/api\/generate\/)\S+/g

export function stripImageMarkup(text: string): string {
  if (!text) return ''
  return text
    .replace(HTML_IMAGE, '')
    .replace(MD_IMAGE, '')
    .replace(BARE_HOST_IMAGE, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n(?:[ \t]*\n){2,}/g, '\n\n')
    .trim()
}
