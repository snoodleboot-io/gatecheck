// hooksmith docs — extra JavaScript
// Loaded after MkDocs Material's own scripts.

document$.subscribe(function () {
  // ── Highlight the install command on click ──────────────────
  const installEl = document.querySelector('.gc-install');
  if (installEl) {
    installEl.style.cursor = 'pointer';
    installEl.title = 'Click to copy';
    installEl.addEventListener('click', function () {
      const cmd = installEl.textContent.replace(/^\s*\$\s*/, '').trim();
      navigator.clipboard.writeText(cmd).then(function () {
        const original = installEl.innerHTML;
        installEl.innerHTML = installEl.innerHTML.replace(
          'pip install hooksmith',
          '<span style="color:#3aad6a">✓ Copied!</span>'
        );
        setTimeout(function () {
          installEl.innerHTML = original;
        }, 1800);
      });
    });
  }

  // ── Annotate external links ─────────────────────────────────
  document.querySelectorAll('.md-content a[href^="http"]').forEach(function (a) {
    if (!a.querySelector('svg') && !a.classList.contains('gc-btn')) {
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
    }
  });

  // ── Version badge in nav ────────────────────────────────────
  const versionSelector = document.querySelector('.md-version__current');
  if (versionSelector) {
    versionSelector.style.color = 'var(--hs-rust-300)';
  }
});
