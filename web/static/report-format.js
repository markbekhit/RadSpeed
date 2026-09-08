/* Copy only the public blank scaffold. No report text is sent or stored. */
(() => {
  const button = document.getElementById('copy-report-format');
  const text = document.getElementById('report-format-text');
  const status = document.getElementById('copy-report-status');
  if (!button || !text || !status) return;
  button.hidden = false;
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text.textContent);
      status.textContent = 'Blank report copied. Replace the bracketed prompts before use.';
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents(text);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = 'Automatic copy is unavailable. The report text is selected; use your usual copy command.';
    }
  });
})();
