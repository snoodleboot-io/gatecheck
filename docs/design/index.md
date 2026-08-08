# Design Documents

These documents capture the design decisions behind hooksmith — both what was built and why alternatives were rejected.

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-top:1.5rem">

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="architecture/">Architecture Overview</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Layered model, data flow, module responsibilities, distribution strategy</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="why-not-precommit/">Why Not pre-commit</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Honest accounting of pre-commit's limitations and the specific problems hooksmith solves</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="rust-core/">Rust Core</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Why Rust, what lives in the Rust layer, the PyO3 boundary, maturin distribution</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="config-design/">Config Design</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Source URI scheme design, TOML vs YAML, the workspace inheritance model</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="monorepo/">Monorepo Model</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Package discovery, dependency graphs, affected set computation</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="environments/">Environment Strategy</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Isolation modes, uv integration, shared envs, cache key design</span>
</div>

<div style="border:1px solid var(--md-default-bg-color--lighter);border-radius:8px;padding:1.25rem">
<strong><a href="versioning/">Versioning & Stability</a></strong><br>
<span style="font-size:.85rem;color:var(--md-default-fg-color--light)">Semantic versioning policy, conventional commits, CI-owned version numbers</span>
</div>

</div>
