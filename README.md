# blueyi.github.io · `yulong.wang`

Personal homepage of **Yulong Wang** — AI Compiler & AI Infra engineer.
A single static page served by GitHub Pages at <https://yulong.wang>.

```
Hero · 4 link cards (Notes / GitHub / Email / Resume)
  │
  └── scroll ──> Stack × Craft
                  ├── Full-stack journey pipeline
                  ├── 6 stack-group chip clusters
                  ├── Highlights
                  └── Currently building
```

## Highlights

- Pure static, single `index.html` — **no build step, no runtime deps**.
- Aurora gradient + grid background, animated hero, scroll-revealed Stack section.
- **Password-gated resume**: client-side AES-GCM, decrypted inside the browser.
- Fully responsive, accessible, and respects `prefers-reduced-motion`.

## Repo layout

| Path                          | Purpose                                                          |
|-------------------------------|------------------------------------------------------------------|
| `index.html`                  | The whole site — inline CSS/JS, no external scripts              |
| `assets/resume.enc.json`      | Encrypted resume blob (AES-GCM, PBKDF2-SHA256 / 250k iters)      |
| `tools/encrypt-resume.html`   | **Offline** browser tool — paste markdown + pass → encrypted JSON|
| `tools/_encrypt_placeholder.mjs` | Node 18+ helper to regenerate a placeholder blob              |
| `tools/README.md`             | Crypto details + security notes                                  |
| `CNAME`                       | GitHub Pages custom domain (`yulong.wang`)                       |
| `404/`, `colorname/`          | Legacy sub-pages (untouched, self-contained)                     |
| `favicon.ico`, `robots.txt`   | Site furniture                                                   |

## Resume — encryption workflow

The resume is **never committed in plaintext**. The repo only ever holds an
encrypted blob that visitors must unlock with a passphrase.

### Quick reference (current setup)

- **Public URL of the encrypted blob:** `https://yulong.wang/assets/resume.enc.json`
- **Cipher:** `AES-256-GCM`
- **KDF:** `PBKDF2-SHA256`, 250,000 iterations
- **The passphrase is shared out-of-band** (over email, chat, etc.) with whoever you want to give resume access to. There is no recovery — losing the passphrase means re-encrypting.

### Updating the resume (recommended, plaintext stays on your machine)

1. Open `tools/encrypt-resume.html` **from disk** (the URL bar should show
   `file://...` — that's the point: no network requests, no upload).
2. Paste your resume Markdown into the textarea. Supports a small Markdown
   subset: `#` headings, `**bold**`, `*italic*`, inline `` `code` ``,
   ```` ``` fenced code ````, `- lists`, `[link](url)`, blank-line
   paragraphs, `---` rules, `> blockquote`. The renderer in the tool
   mirrors what visitors see after unlocking.
3. Enter your passphrase twice (must match). Choose **strong, memorable**;
   long passphrases beat short complex ones.
4. Click **Encrypt &amp; preview**, then **Download resume.enc.json**.
5. Replace the committed blob and push:
   ```bash
   mv ~/Downloads/resume.enc.json assets/resume.enc.json
   git add assets/resume.enc.json
   git commit -m "chore(resume): refresh encrypted resume"
   git push
   ```
6. Reload `https://yulong.wang`, click **Resume**, enter the passphrase — done.

### Updating the resume (CLI / Node ≥ 18, plaintext passes through shell)

If you'd rather batch-encrypt from a terminal, a one-liner using Node's
built-in Web Crypto API works:

```bash
# Edit the input path / output path / passphrase as needed.
RESUME_IN=/path/to/resume.md \
RESUME_OUT=assets/resume.enc.json \
RESUME_PASS='your strong passphrase' \
node -e '
const fs = require("fs");
(async () => {
  const pt = fs.readFileSync(process.env.RESUME_IN, "utf8");
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv   = crypto.getRandomValues(new Uint8Array(12));
  const km   = await crypto.subtle.importKey("raw", new TextEncoder().encode(process.env.RESUME_PASS), "PBKDF2", false, ["deriveKey"]);
  const key  = await crypto.subtle.deriveKey({name:"PBKDF2",hash:"SHA-256",salt,iterations:250000}, km, {name:"AES-GCM",length:256}, false, ["encrypt"]);
  const ct   = await crypto.subtle.encrypt({name:"AES-GCM",iv}, key, new TextEncoder().encode(pt));
  const b64  = (b) => Buffer.from(b).toString("base64");
  fs.writeFileSync(process.env.RESUME_OUT, JSON.stringify({
    v:1, kdf:"PBKDF2-SHA256", iter:250000, cipher:"AES-GCM",
    salt:b64(salt), iv:b64(iv), ct:b64(ct)
  }, null, 2) + "\n");
})();'
```

Beware shell history — quote the passphrase carefully, or read it from a
file instead of `RESUME_PASS=...` if your terminal logs commands.

### How a visitor reads it

1. On `https://yulong.wang`, click the **Resume (locked)** card.
2. A modal asks for the passphrase. The page fetches `assets/resume.enc.json`.
3. The browser derives the AES key (`PBKDF2-SHA256`, 250k iters) from the
   passphrase and the blob's salt, then decrypts with `AES-GCM` using the
   blob's IV. The decrypted Markdown is rendered into the modal.
4. Wrong passphrase → AES-GCM auth tag fails → friendly error, no leak,
   no garbage output.
5. Click **re-lock** (or close the modal) to clear the decrypted text.
   It is never persisted — reload the page and you have to unlock again.

### Security trade-offs

- The blob is **public**. An attacker can grab it and run an *offline*
  PBKDF2 attack indefinitely. Your **passphrase entropy** is the only
  defense. A long random phrase (6+ unrelated words) is fine; "p4ssw0rd!"
  is not.
- Want stronger guarantees (rate limiting, revocation, audit)? Move the
  resume off the static site and behind a real auth endpoint
  (e.g. Cloudflare Workers + Turnstile). The static-site gate here is for
  *casually private* — keeping the resume out of search indexers and
  casual link-sharers, while still being deployable on a 100% static host.

For the longer write-up of the crypto, see [`tools/README.md`](tools/README.md).

## Local preview

```bash
python3 -m http.server 8765
# then open http://localhost:8765
```

## License

Personal site content — all rights reserved unless explicitly noted.
The page layout / CSS scaffolding is yours to reuse if you find it useful.
