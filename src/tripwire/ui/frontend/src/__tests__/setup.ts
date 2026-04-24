import "@testing-library/jest-dom/vitest";

// Radix UI primitives (DropdownMenu, Popover, Dialog) use pointer-capture
// APIs and scrollIntoView during open/close transitions; jsdom implements
// none of these. Patch with no-ops so fireEvent.click on a trigger actually
// opens the content in tests.
if (typeof Element !== "undefined") {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => {};
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => {};
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
}
