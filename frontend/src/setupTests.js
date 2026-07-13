import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement scrollIntoView — App.jsx calls it to keep the chat scrolled to the latest message.
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = () => {}
}
