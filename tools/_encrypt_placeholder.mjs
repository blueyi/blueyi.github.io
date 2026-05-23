// One-off helper to generate a placeholder assets/resume.enc.json
// using the SAME crypto params as tools/encrypt-resume.html and the page-side decryption.
// Run: node tools/_encrypt_placeholder.mjs > assets/resume.enc.json
//
// This file is NOT used at runtime by the site. Safe to keep for regeneration.
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const ITER = 250000;
const PASSPHRASE = process.env.RESUME_PASS ?? 'demo';
const OUT = process.argv[2] ?? resolve(dirname(fileURLToPath(import.meta.url)), '../assets/resume.enc.json');

const PLAINTEXT = `# Resume — preview

> 👋 This is a **placeholder**. The site owner will replace it with the real resume,
> encrypted via \`tools/encrypt-resume.html\`. The demo passphrase for this placeholder is \`demo\`.

## About

I work at the intersection of **AI Infra** and **LLM / Agent systems** — making large
models run fast on heterogeneous hardware (GPU / NPU), and building agentic workflows
that actually ship.

## Expanding to full-stack LLM & AI Infra

- Data — corpora curation, RAG indexing, retrieval evaluation
- Pre-train — distributed pre-training, tokenizer & data ops
- Fine-tune — SFT, LoRA / QLoRA, RLHF / DPO
- Serve — vLLM, SGLang, TensorRT-LLM, paged KV cache, FlashAttention
- Agent — MCP, Claude Code, LangGraph, tool calling, planners
- Eval — agent eval, bench, observability
- Ops — Kubernetes, NCCL / HCCL, Nsight, perf

## Skills

- **Languages**: C++, Python, Go, Bash
- **AI Infra**: CUDA, Triton, Ascend CANN, NPU IR, NCCL / HCCL
- **LLM**: PyTorch, Megatron-LM, DeepSpeed, HuggingFace, vLLM, TensorRT-LLM
- **Systems**: Linux, Docker, Kubernetes, profiling (Nsight, perf)

## Contact

- Email: \`yl.w@outlook.com\`
- Notes: \`notes.maxwi.com\`
- GitHub: \`@blueyi\`

---

*The real resume content is private. Encrypt yours locally with \`tools/encrypt-resume.html\`
and commit the resulting \`assets/resume.enc.json\` to replace this placeholder.*
`;

const b64 = (buf) => Buffer.from(buf).toString('base64');
const salt = crypto.getRandomValues(new Uint8Array(16));
const iv = crypto.getRandomValues(new Uint8Array(12));
const keyMaterial = await crypto.subtle.importKey('raw', new TextEncoder().encode(PASSPHRASE), 'PBKDF2', false, ['deriveKey']);
const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations: ITER },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt']
);
const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(PLAINTEXT));

const out = {
    v: 1,
    kdf: 'PBKDF2-SHA256',
    iter: ITER,
    cipher: 'AES-GCM',
    salt: b64(salt),
    iv: b64(iv),
    ct: b64(ct)
};

writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n');
console.error(`wrote ${OUT} (${JSON.stringify(out).length} bytes) — passphrase: ${PASSPHRASE}`);
