# tools/

Helpers for the password-gated resume on the homepage.

## How the resume gate works

The homepage ships an `assets/resume.enc.json` blob. When a visitor clicks
**Resume**, the modal prompts for a passphrase and decrypts the blob entirely
client-side using the Web Crypto API:

- KDF: `PBKDF2-SHA256`, 250,000 iterations
- Key:  256-bit AES-GCM
- Random 16-byte salt, random 12-byte IV (regenerated every encryption)
- Output JSON shape:
  ```json
  {
    "v": 1,
    "kdf": "PBKDF2-SHA256",
    "iter": 250000,
    "cipher": "AES-GCM",
    "salt": "<base64>",
    "iv":   "<base64>",
    "ct":   "<base64>"
  }
  ```

Because AES-GCM authenticates the ciphertext, a wrong passphrase always
fails decryption — there is no chance of returning garbage on a bad key.

## Replacing the placeholder resume

> The repo currently ships a **placeholder** encrypted with passphrase `demo`.
> You should replace it with your real resume + a real passphrase before
> sharing the site link with anyone.

### Recommended path (plaintext never leaves your machine)

1. **Download `tools/encrypt-resume.html`** (or clone the repo) and open the
   file from disk in your browser. The URL bar should show `file://...` —
   that's the point: there is no network request, no analytics, no upload.
2. Paste your resume Markdown into the textarea.
   - Supports a small Markdown subset: `#` headings, `**bold**`, `*italic*`,
     inline `` `code` ``, ```` ``` fenced code ````, `- lists`, `[link](url)`,
     blank-line paragraphs, `---` horizontal rules, `> blockquote`.
   - The same tiny renderer ships in `index.html`, so the preview in the
     tool mirrors what visitors will see after unlocking.
3. Pick a strong passphrase (and confirm it). There is **no recovery** — if
   you lose it, you must re-encrypt and commit a new blob.
4. Click **Encrypt & preview** → **Download resume.enc.json**.
5. Replace `assets/resume.enc.json` with the downloaded file:
   ```bash
   mv ~/Downloads/resume.enc.json assets/resume.enc.json
   git add assets/resume.enc.json
   git commit -m "chore(resume): refresh encrypted resume"
   git push
   ```
6. Visit your site, click **Resume**, enter the passphrase — done.

### Alternative path (CLI, requires Node ≥ 18)

If you'd rather encrypt from a terminal, you can repurpose
`tools/_encrypt_placeholder.mjs`:

```bash
RESUME_PASS="your strong passphrase" \
  node tools/_encrypt_placeholder.mjs ./assets/resume.enc.json
```

Note: this script embeds the placeholder text. To encrypt your real resume,
edit the `PLAINTEXT` constant first (or write a tiny variant that reads from
a file). Be careful with shell history if your passphrase is sensitive.

## Security notes

- This is the **best you can do** on a fully static GitHub Pages site:
  the encrypted blob is public, and the only secret is the passphrase.
- Use a **long, high-entropy passphrase** (think 6+ unrelated words, or a
  random 16+ char string). Anyone can attempt an *offline* brute-force on
  the blob, so the PBKDF2 work factor (250k iters) and passphrase entropy
  are your only defenses.
- The tool sets `PBKDF2` iterations to **250k** by default; you can bump
  this in the tool's UI for an even slower derivation (at the cost of a
  longer unlock delay for visitors).
- Once unlocked in a browser tab, the decrypted text lives in memory for
  that session only. The page does not persist it; reloading the page or
  clicking **re-lock** clears it.
- Want stronger guarantees (rate-limiting, audit logs, revocation)? Move
  the resume off the static site and behind a real auth-gated endpoint
  (e.g. Cloudflare Workers + Turnstile). The static-site gate here is
  designed for "casually private" — keeping the resume out of search
  indexers and casual link-sharers.

## Files

| File                          | Purpose                                                       |
|-------------------------------|---------------------------------------------------------------|
| `tools/encrypt-resume.html`   | Offline browser tool — paste markdown + pass → encrypted JSON |
| `tools/_encrypt_placeholder.mjs` | Node script that generates the demo placeholder blob       |
| `assets/resume.enc.json`      | The encrypted blob the page fetches and decrypts              |
