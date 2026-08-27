const docx = require("docx");
const fs = require("fs");

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType,
  PageBreak, Header, Footer, PageNumber,
  convertInchesToTwip, TableOfContents,
} = docx;

const PETROL = "1A1A2E";
const TWILIGHT = "2C5F7C";
const ACCENT = "B85C38";
const GRAY = "666666";

function ar(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.RIGHT,
    spacing: { after: opts.after || 200, line: opts.line || 360 },
    children: [
      new TextRun({ text, font: "Tahoma", size: opts.size || 24, color: opts.color || "333333", bold: opts.bold || false }),
    ],
  });
}

function heading1(ar, en) {
  return [
    new Paragraph({ spacing: { before: 400, after: 100 }, children: [] }),
    new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.RIGHT, spacing: { after: 60 }, children: [new TextRun({ text: ar, font: "Tahoma", size: 32, bold: true, color: PETROL })] }),
    new Paragraph({ heading: HeadingLevel.HEADING_2, alignment: AlignmentType.LEFT, spacing: { after: 200 }, children: [new TextRun({ text: en, font: "Calibri", size: 24, color: TWILIGHT, italics: true })] }),
  ];
}

function heading2(ar, en) {
  return [
    new Paragraph({ spacing: { before: 250, after: 80 }, children: [] }),
    new Paragraph({ heading: HeadingLevel.HEADING_3, alignment: AlignmentType.RIGHT, spacing: { after: 40 }, children: [new TextRun({ text: ar, font: "Tahoma", size: 26, bold: true, color: ACCENT })] }),
    new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 150 }, children: [new TextRun({ text: en, font: "Calibri", size: 20, color: GRAY, italics: true })] }),
  ];
}

function bullet(text) {
  return new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { after: 100, line: 340 }, indent: { right: convertInchesToTwip(0.4) }, children: [
    new TextRun({ text: "\u2022  ", font: "Tahoma", size: 22, color: ACCENT }),
    new TextRun({ text, font: "Tahoma", size: 22, color: "444444" }),
  ] });
}

function tRow(cells, hdr) {
  return new TableRow({ tableHeader: !!hdr, children: cells.map(([t, w]) => new TableCell({
    width: { size: w, type: WidthType.PERCENTAGE },
    shading: { type: ShadingType.CLEAR, fill: hdr ? PETROL : "FFFFFF", color: "auto" },
    children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { before: 60, after: 60 }, children: [new TextRun({ text: t, font: "Tahoma", size: 20, color: hdr ? "FFFFFF" : "444444", bold: !!hdr })] })],
  })) });
}

function makeTable(headers, rows, widths) {
  return new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, columnWidths: widths, rows: [
    tRow(headers.map((h, i) => [h, widths[i]]), true),
    ...rows.map(r => tRow(r.map((c, i) => [c, widths[i]])))
  ] });
}

// ═══ BUILD ═══
const C = [];

// Title page
C.push(
  new Paragraph({ spacing: { before: 2000 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [new TextRun({ text: "\u0627\u0644\u0641\u0631\u064A\u062C \u0627\u0644\u0639\u0642\u0627\u0631\u064A", font: "Tahoma", size: 56, bold: true, color: PETROL })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "AL-FURAJ REAL ESTATE", font: "Calibri", size: 32, color: TWILIGHT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [new TextRun({ text: "\u062F\u0644\u064A\u0644 \u0627\u0644\u0645\u0646\u0635\u0629 \u0627\u0644\u0634\u0627\u0645\u0644", font: "Tahoma", size: 28, color: ACCENT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: "Complete Platform Guide", font: "Calibri", size: 24, color: GRAY, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "\u0627\u0644\u0625\u0635\u062F\u0627\u0631: \u0627\u0646\u062A\u0631\u0646\u062A 2026", font: "Tahoma", size: 22, color: GRAY })] }),
  new Paragraph({ children: [new PageBreak()] })
);

// TOC
C.push(...heading1("\u0641\u0647\u0631\u0633 \u0627\u0644\u0645\u0648\u0627\u0642\u0639", "Table of Contents"));
C.push(new TableOfContents("Guide", { hyperlink: true, headingStyleRange: "1-3" }));
C.push(new Paragraph({ children: [new PageBreak()] }));

// Section 1: Overview
C.push(...heading1("\u0645\u0644\u062E\u0635 \u0628\u0627\u0644\u0645\u0646\u0635\u0629", "Platform Overview"));
C.push(ar("\u0645\u0646\u0635\u0629 \u0627\u0644\u0641\u0631\u064A\u062C \u0647\u064A \u0645\u0646\u0635\u0629 \u0639\u0642\u0627\u0631\u064A\u0629 \u0634\u0627\u0645\u0644\u0629 \u062A\u0628\u062D\u062B \u0641\u064A \u0628\u064A\u0626\u0627\u0639\u0627\u062A \u0627\u0644\u0641\u0631\u064A\u062C \u0627\u0644\u0639\u0642\u0627\u0631\u064A \u0648\u062A\u0642\u064A\u0645\u0647\u0627 \u0628\u0627\u0644\u0642\u064A\u0645\u0629 \u0627\u0644\u0633\u0648\u0642\u064A\u0629 \u0627\u0644\u062A\u0642\u062F\u064A\u0631\u064A\u0629."));
C.push(ar("\u062A\u0645\u064A\u0632 \u0627\u0644\u0645\u0646\u0635\u0629 \u0628\u0627\u0644\u0628\u062D\u062B \u0627\u0644\u0630\u0643\u064A \u0639\u0646 \u0637\u0631\u064A\u0642 \u0627\u0644\u0644\u063A\u0629 \u0627\u0644\u0637\u0628\u064A\u0639\u064A\u0629 \u0627\u0644\u0639\u0631\u0628\u064A\u0629."));

C.push(makeTable(
  ["\u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0629", "\u0627\u0644\u0642\u064A\u0645\u0629", "\u0627\u0644\u062D\u0627\u0644\u0629"],
  [
    ["\u0625\u0639\u0644\u0627\u0646\u0627\u062A \u0627\u0644\u0641\u0631\u064A\u062C", "182", "\u0645\u062A\u0635\u0644\u0645\u0629"],
    ["\u0625\u0639\u0644\u0627\u0646\u0627\u062A \u0627\u0644\u0645\u0648\u0627\u0642\u0639 \u0627\u0644\u062E\u0627\u0631\u062C\u064A\u0629", "2700+", "\u0645\u0646 6 \u0645\u0635\u0627\u062F\u0631"],
    ["\u0641\u0631\u0635 \u0627\u0644\u0645\u0643\u0633\u0628", "421/695", "\u062A\u0644\u0642\u0627\u0626\u064A\u0629"],
    ["\u0625\u0639\u0644\u0627\u0646\u0627\u062A \u0627\u0644\u0633\u0648\u0642", "999+", "\u0645\u062A\u062D\u062F\u062B\u0629"],
  ],
  [35, 35, 30]
));
C.push(new Paragraph({ spacing: { after: 300 }, children: [] }));

// Section 2: Features
C.push(...heading1("\u0627\u0644\u0645\u064A\u0632\u0627\u062A \u0627\u0644\u0631\u0626\u064A\u0633\u064A\u0629", "Key Features"));

C.push(...heading2("1. \u0627\u0644\u0628\u062D\u062B \u0627\u0644\u0630\u0643\u064A", "Smart Real Estate Search"));
C.push(ar("\u064A\u0633\u0645\u062D \u0644\u0643 \u0627\u0644\u0628\u062D\u062B \u0628\u0627\u0644\u0644\u063A\u0629 \u0627\u0644\u0637\u0628\u064A\u0639\u064A\u0629 \u0628\u0637\u0631\u064A\u0642\u0629 \u0628\u0633\u064A\u062A\u0629."));
C.push(bullet("\u0628\u062D\u062B \u0645\u0646 \u0645\u0635\u0627\u062F\u0631 \u0645\u062E\u062A\u0644\u0641\u0629: \u0627\u0644\u0641\u0631\u064A\u062C + OpenSooq + Mourjan + 4Sale + FindQ8"));
C.push(bullet("\u0627\u0644\u062A\u0648\u0641\u064A\u0642 \u0627\u0644\u0630\u0643\u064A: \u0645\u0631\u0627\u062C\u0639\u0629 \u0639\u0642\u0627\u0631\u064A\u0629 \u0645\u0646 \u0645\u0635\u062F\u0631\u064A\u0646 \u0645\u062E\u062A\u0644\u0641\u064A\u0646"));
C.push(bullet("\u062A\u0642\u064A\u064A\u0645 \u0627\u0644\u0639\u0642\u0627\u0631 \u0628\u0627\u0644\u0645\u0642\u0627\u0631\u0646\u0629 \u0627\u0644\u0645\u062D\u0644\u064A\u0629"));

C.push(...heading2("2. \u0627\u0644\u062A\u0642\u064A\u064A\u0645 \u0627\u0644\u0645\u0642\u0627\u0631\u0646 \u0627\u0644\u0630\u0643\u064A", "Smart Comparative Valuation"));
C.push(ar("\u064A\u0642\u064A\u0645 \u0643\u0644 \u0639\u0642\u0627\u0631 \u0628\u0627\u0644\u0642\u064A\u0645\u0629 \u0627\u0644\u0633\u0648\u0642\u064A\u0629 \u0627\u0644\u062A\u0642\u062F\u064A\u0631\u064A\u0629."));
C.push(bullet("\u062C\u062D\u0632 \u0623\u0633\u0639\u0627\u0631 \u0627\u0644\u0645\u062A\u0631 \u0627\u0644\u0645\u062A\u0648\u0642\u0639\u0629 \u0641\u064A \u0627\u0644\u0645\u0646\u0637\u0642\u0629"));
C.push(bullet("\u062D\u0643\u0645: \u0644\u0642\u0637\u0629 / \u0639\u0627\u062F\u064A / \u063A\u0627\u0644\u064A"));
C.push(bullet("\u0627\u0644\u0639\u0627\u0626\u062F \u0627\u0644\u0625\u064A\u062C\u0627\u0631\u064A \u0627\u0644\u0633\u0646\u0648\u064A"));

C.push(...heading2("3. \u0641\u0631\u0635 \u0627\u0644\u0645\u0643\u0633\u0628", "Profit Opportunities"));
C.push(ar("\u062A\u0631\u0635\u062F \u0641\u0631\u0635 \u0645\u0643\u0633\u0628 \u062A\u0642\u064A\u0645\u064A\u0629 \u0628\u0648\u0627\u0633\u0637\u0629 \u0627\u0644\u0639\u0631\u0636 \u0628\u0627\u0644\u0637\u0644\u0628."));
C.push(bullet("\u0627\u0644\u0631\u0635\u0645 \u0627\u0644\u0628\u064A\u0639\u064A \u0628\u0627\u0644\u0633\u0639\u0631 \u0627\u0644\u0645\u062A\u0648\u0642\u0639"));
C.push(bullet("\u0627\u0644\u0641\u0631\u0642 \u0628\u064A\u0646 \u0633\u0639\u0631 \u0627\u0644\u0639\u0631\u0636 \u0648\u0627\u0644\u0633\u0639\u0631 \u0627\u0644\u0645\u062A\u0648\u0642\u0639"));

C.push(...heading2("4. \u0627\u0644\u0645\u0633\u0627\u0639\u062F \u0627\u0644\u0630\u0643\u064A", "AI-Powered Assistant"));
C.push(ar("\u0645\u0633\u0627\u0639\u062F \u0639\u0642\u0627\u0631\u064A \u0628\u0627\u0644\u0628\u062D\u062B \u0627\u0644\u0630\u0643\u064A \u0628\u0633\u0631\u0639\u0629 \u0641\u0648\u0631\u064A\u0629."));
C.push(bullet("\u0627\u0644\u0628\u062D\u062B \u0628\u0627\u0644\u0644\u063A\u0629 \u0627\u0644\u0637\u0628\u064A\u0639\u064A\u0629 \u0627\u0644\u0639\u0631\u0628\u064A\u0629"));
C.push(bullet("\u0627\u0644\u0623\u0633\u062A\u0639\u0644\u0627\u0645 \u0628\u0627\u0644\u0644\u063A\u0629 \u0627\u0644\u0645\u0628\u0633\u0637\u0629"));
C.push(bullet("\u062A\u0631\u062C\u064A\u0639 \u0627\u0644\u0646\u062A\u0627\u0626\u062C \u0628\u0635\u064A\u063A\u0629 PDF \u0648\u0625\u0643\u0633\u0644"));

// Section 3: Getting Started
C.push(...heading1("\u0628\u062F\u0621 \u0627\u0644\u0627\u0633\u062A\u062E\u062F\u0627\u0645", "Getting Started"));
C.push(ar("\u0644\u0644\u0628\u062F\u0621 \u0627\u0633\u062A\u062E\u062F\u0627\u0645 \u0627\u0644\u0645\u0646\u0635\u0629:", { bold: true }));
C.push(bullet("1. \u0639\u0645\u0644 \u0628\u0631\u0646\u0627\u0645\u062C \u00AB\u062D\u0633\u0627\u0628\u064A\u00BB \u0628\u0631\u0642\u0645 \u0627\u0644\u0647\u0627\u062A\u0641 \u0623\u0648 Google"));
C.push(bullet("2. \u0627\u0643\u062A\u0628 \u0637\u0644\u0628\u0643 \u0627\u0644\u0639\u0642\u0627\u0631\u064A"));
C.push(bullet("3. \u0627\u062E\u062A\u0631 \u0646\u0637\u0642\u0629 \u0627\u0644\u0645\u0635\u062F\u0631"));
C.push(bullet("4. \u0627\u0631\u062C\u0639 \u0627\u0644\u0646\u062A\u0627\u0626\u062C \u0627\u0644\u0645\u0634\u062A\u0645\u0644\u0629"));
C.push(bullet("5. \u062D\u0641\u0638 \u0627\u0644\u0628\u062D\u062B \u0644\u0644\u062A\u0646\u0628\u064A\u0647"));

// Section 4: Tech
C.push(...heading1("\u0627\u0644\u0645\u0639\u0645\u0627\u0631\u064A\u0629 \u0627\u0644\u0641\u0646\u064A\u0629", "Technical Architecture"));
C.push(bullet("Python + ThreadingHTTPServer"));
C.push(bullet("Supabase (PostgreSQL)"));
C.push(bullet("Vanilla JavaScript + CSS"));
C.push(bullet("OpenAI API"));
C.push(bullet("OTP + Google Identity Services"));

// Section 5: Data Sources
C.push(...heading1("\u0645\u0635\u0627\u062F\u0631 \u0627\u0644\u0628\u064A\u0627\u0646\u0627\u062A", "Data Sources"));
C.push(makeTable(
  ["\u0627\u0644\u0645\u0635\u062F\u0631", "\u0627\u0644\u0639\u062F\u062F", "\u0627\u0644\u0648\u0635\u0641"],
  [
    ["\u0627\u0644\u0641\u0631\u064A\u062C", "182", "\u0628\u064A\u0627\u0646\u0627\u062A \u0645\u062D\u0644\u064A\u0629"],
    ["OpenSooq", "1150+", "\u0627\u0644\u0645\u0648\u0642\u0639 \u0627\u0644\u0639\u0642\u0627\u0631\u064A \u0627\u0644\u0623\u0643\u0628\u0631"],
    ["4Sale", "480+", "\u0645\u0646\u0635\u0629 \u0627\u0644\u0628\u064A\u0639"],
    ["Mourjan", "260+", "\u0627\u0644\u0645\u0648\u0642\u0639 \u0627\u0644\u0639\u0642\u0627\u0631\u064A \u0627\u0644\u0633\u0639\u0648\u062F\u064A"],
    ["FindQ8", "15", "\u0628\u062D\u062B \u0645\u0648\u062D\u062F"],
    ["KFH Reports", "4", "\u062A\u0642\u0627\u0631\u064A\u0631 \u0639\u0642\u0627\u0631\u064A\u0629"],
  ],
  [30, 20, 50]
));
C.push(new Paragraph({ spacing: { after: 300 }, children: [] }));

// Section 6: Auth
C.push(...heading1("\u0646\u0638\u0627\u0645 \u062A\u0633\u062C\u064A\u0644 \u0627\u0644\u062F\u062E\u0648\u0644", "Authentication"));
C.push(bullet("\u0627\u0644\u062F\u062E\u0648\u0644 \u0628\u0631\u0642\u0645 \u0627\u0644\u0647\u0627\u062A\u0641 \u0628\u0645\u0631\u0627\u0633\u0644 OTP"));
C.push(bullet("\u0627\u0644\u062F\u062E\u0648\u0644 \u0628\u062D\u0633\u0627\u0628 Google"));
C.push(bullet("\u062A\u0633\u062C\u064A\u0644 \u0627\u0644\u062E\u0631\u0648\u062C \u0628\u0633\u0647\u0648\u0644\u0629"));

// Section 7: API
C.push(...heading1("\u0645\u0631\u062C\u0639 \u0627\u0644\u0628\u0631\u0627\u0645\u062C", "API Reference"));
C.push(makeTable(
  ["\u0627\u0644\u0645\u0633\u0627\u0631", "\u0627\u0644\u0637\u0631\u064A\u0642", "\u0627\u0644\u0648\u0635\u0641"],
  [
    ["/api/analyze", "POST", "\u062a\u062d\u0644\u064a\u0644 \u0628\u062d\u062b"],
    ["/api/google-login", "POST", "\u062a\u0633\u062c\u064a\u0644 \u0628\u062d\u0633\u0627\u0628 Google"],
    ["/api/health", "GET", "\u062d\u0627\u0644\u0629 \u0627\u0644\u062e\u0627\u062f\u0645"],
    ["/api/analytics-dashboard", "GET", "\u0644\u0648\u062d\u0629 \u0627\u0644\u062a\u062d\u0644\u064a\u0644\u0627\u062a"],
    ["/api/opportunities", "GET", "\u0641\u0631\u0635 \u0627\u0644\u0645\u0643\u0633\u0628"],
  ],
  [25, 15, 60]
));
C.push(new Paragraph({ spacing: { after: 300 }, children: [] }));

// Footer
C.push(
  new Paragraph({ spacing: { before: 400 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "\u2014 \u0645\u0646\u0635\u0629 \u0627\u0644\u0641\u0631\u064A\u062C \u0644\u0644\u0641\u0631\u0635 \u0648\u0627\u0644\u062a\u0642\u064a\u064a\u0645 \u0627\u0644\u0639\u0642\u0627\u0631\u064a \u2014 2026 \u2014", font: "Tahoma", size: 20, color: GRAY, italics: true }),
  ] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "Generated with Codebuff", font: "Calibri", size: 18, color: GRAY }),
  ] }),
);

// ═══ SAVE ═══
const doc = new Document({
  creator: "Al-Furaj Platform",
  title: "\u062f\u0644\u064a\u0644 \u0627\u0644\u0645\u0646\u0635\u0629",
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: convertInchesToTwip(1), bottom: convertInchesToTwip(1), left: convertInchesToTwip(1.2), right: convertInchesToTwip(1.2) },
      },
    },
    headers: { default: new Header({ children: [
      new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "\u0627\u0644\u0641\u0631\u064A\u062C \u0627\u0644\u0639\u0642\u0627\u0631\u064A", font: "Tahoma", size: 18, color: GRAY })] }),
    ] }) },
    footers: { default: new Footer({ children: [
      new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: "\u0627\u0644\u0635\u0641\u062d\u0629 ", font: "Tahoma", size: 18, color: GRAY }),
        new TextRun({ children: [PageNumber.CURRENT], font: "Calibri", size: 18, color: GRAY }),
      ] }),
    ] }) },
    children: C,
  }],
});

const out = "docs/alforaij_platform_guide.docx";
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(out, buf);
  console.log("Document saved: " + out);
  console.log("Size: " + (buf.length / 1024).toFixed(1) + " KB");
}).catch(err => console.error("Error:", err));
