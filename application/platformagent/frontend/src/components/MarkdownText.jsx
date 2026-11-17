import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MD_MODES } from '../constants.js';

export function resolveMdMode(message, globalMode) {
  return message.mdView && message.mdView !== globalMode ? message.mdView : globalMode;
}

export function isMdOverridden(message, globalMode) {
  return Boolean(message.mdView) && message.mdView !== globalMode;
}

// react-markdown v9+ 会把 AST node 一并塞进自定义组件的 props，必须解构掉，
// 否则 React 会对 <a> 报 "does not recognize the `node` prop on a DOM element"。
function MarkdownLink({ node, ...props }) {
  return <a {...props} target="_blank" rel="noreferrer noopener" />;
}

// 原文模式直接返回字符串，沿用外层容器既有的 white-space: pre-wrap 原样回显。
export default function MarkdownText({ content, mode }) {
  if (mode !== MD_MODES.formatted) return content;
  // react-markdown 默认跳过内联原始 HTML（不引 rehype-raw），模型输出里的
  // <script> 等不会被注入，因此无需 dangerouslySetInnerHTML。
  return <div className="md-body">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>{content}</ReactMarkdown>
  </div>;
}

