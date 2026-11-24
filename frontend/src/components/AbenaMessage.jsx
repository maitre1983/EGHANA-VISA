import React from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";

const SAFE_EXTERNAL = /^(https:\/\/|mailto:|tel:)/i;

function MdLink({ href = "", children }) {
    if (href.startsWith("/") && !href.startsWith("//")) {
        return <Link to={href} className="text-ghana-green font-semibold underline underline-offset-2 hover:text-ghana-green-dark">{children}</Link>;
    }
    if (SAFE_EXTERNAL.test(href)) {
        return <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-ghana-green font-semibold underline underline-offset-2">{children}</a>;
    }
    return <span>{children}</span>;
}

const components = {
    p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
    strong: ({ children }) => <strong className="font-semibold text-ghana-black">{children}</strong>,
    em: ({ children }) => <em>{children}</em>,
    ul: ({ children }) => <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-1">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed pl-0.5">{children}</li>,
    a: MdLink,
    h1: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
    h2: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
    h3: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
    code: ({ children }) => <span className="font-mono text-[0.85em] bg-slate-100 rounded px-1">{children}</span>,
    hr: () => null,
    img: () => null,
    table: ({ children }) => <div className="overflow-x-auto">{children}</div>,
};

export function AbenaMessage({ text, user }) {
    if (user) return <div className="whitespace-pre-wrap">{text}</div>;
    return (
        <div data-testid="abena-message-md" className="abena-md">
            <ReactMarkdown components={components} skipHtml>{text}</ReactMarkdown>
        </div>
    );
}
