<template>
  <div class="markdown-body" @click="onCopyClick" v-html="safeHtml"></div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import yaml from 'highlight.js/lib/languages/yaml'
import markdown from 'highlight.js/lib/languages/markdown'
import java from 'highlight.js/lib/languages/java'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import php from 'highlight.js/lib/languages/php'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import diff from 'highlight.js/lib/languages/diff'
import 'highlight.js/styles/github.css'

const props = defineProps({
  content: { type: String, default: '' }
})

for (const [name, language] of Object.entries({
  javascript,
  typescript,
  python,
  bash,
  json,
  sql,
  xml,
  css,
  yaml,
  markdown,
  java,
  go,
  rust,
  cpp,
  csharp,
  php,
  dockerfile,
  diff
})) {
  hljs.registerLanguage(name, language)
}

const aliases = {
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  yml: 'yaml',
  md: 'markdown',
  html: 'xml',
  vue: 'xml',
  'c++': 'cpp',
  cs: 'csharp',
  'c#': 'csharp',
  docker: 'dockerfile'
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true
})

// 链接统一新窗口打开
const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

// 代码块：语言标签 + 复制按钮 + 高亮
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : ''
  const lang = info.split(/\s+/)[0] || ''
  const canonical = aliases[lang.toLowerCase()] || lang.toLowerCase()
  const code = token.content

  let highlighted
  if (canonical && hljs.getLanguage(canonical)) {
    highlighted = hljs.highlight(code, {
      language: canonical,
      ignoreIllegals: true
    }).value
  } else {
    highlighted = md.utils.escapeHtml(code)
  }

  const label = md.utils.escapeHtml(lang || 'text')
  const encoded = encodeURIComponent(code)
  return (
    '<div class="md-code">' +
    '<div class="md-code-head">' +
    `<span>${label}</span>` +
    `<button type="button" class="md-copy" data-code="${encoded}">复制</button>` +
    '</div>' +
    `<pre class="hljs"><code class="language-${md.utils.escapeHtml(canonical || 'text')}">${highlighted}</code></pre>` +
    '</div>'
  )
}

const safeHtml = computed(() =>
  DOMPurify.sanitize(md.render(props.content || ''), {
    ADD_ATTR: ['target', 'rel', 'data-code'],
    FORBID_TAGS: ['style', 'form', 'input', 'iframe', 'textarea'],
    FORBID_ATTR: ['style', 'contenteditable']
  })
)

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  document.execCommand('copy')
  document.body.removeChild(area)
}

async function onCopyClick(event) {
  const button = event.target.closest('.md-copy')
  if (!button) return
  try {
    await copyText(decodeURIComponent(button.dataset.code || ''))
    const original = button.textContent
    button.textContent = '已复制'
    setTimeout(() => {
      button.textContent = original
    }, 1500)
  } catch {
    button.textContent = '复制失败'
    setTimeout(() => {
      button.textContent = '复制'
    }, 1500)
  }
}
</script>

<style scoped>
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.markdown-body :deep(> :first-child) {
  margin-top: 0;
}

.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 14px 0 8px;
  font-weight: 600;
  line-height: 1.35;
}

.markdown-body :deep(h1) {
  font-size: 20px;
}

.markdown-body :deep(h2) {
  font-size: 18px;
}

.markdown-body :deep(h3) {
  font-size: 16px;
}

.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-size: 14px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 8px;
  padding-left: 1.5em;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(li > p) {
  margin: 0;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 10px;
  border-left: 3px solid #d1d5db;
  border-radius: 4px;
  background: #f9fafb;
  color: #4b5563;
}

.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(hr) {
  border: 0;
  border-top: 1px solid #e5e7eb;
  margin: 12px 0;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

.markdown-body :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(17, 24, 39, 0.07);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.92em;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  font-size: 13px;
}

.markdown-body :deep(table) {
  display: block;
  max-width: 100%;
  margin: 8px 0;
  overflow-x: auto;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 5px 10px;
  border: 1px solid #e5e7eb;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f9fafb;
  font-weight: 600;
}

.markdown-body :deep(.md-code) {
  margin: 8px 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.markdown-body :deep(.md-code-head) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  background: #f3f4f6;
  border-bottom: 1px solid #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.6;
}

.markdown-body :deep(.md-copy) {
  padding: 2px 4px;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 12px;
  cursor: pointer;
}

.markdown-body :deep(.md-copy:hover) {
  text-decoration: underline;
}

.markdown-body :deep(.md-code pre) {
  margin: 0;
  padding: 10px 12px;
  overflow-x: auto;
  background: #fff;
}

.markdown-body :deep(.md-code .hljs) {
  background: #fff;
}
</style>
