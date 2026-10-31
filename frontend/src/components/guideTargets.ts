export function findGuideTarget(selector: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll<HTMLElement>(selector)).find(element =>
    !element.closest('[hidden], [aria-hidden="true"]') && element.getClientRects().length > 0
      && getComputedStyle(element).visibility !== 'hidden')
}
