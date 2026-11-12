import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfidenceMeter } from "@/design-system/components/confidence-meter";
import { DraftText } from "@/design-system/components/draft-text";
import { InboxItem } from "@/design-system/components/inbox-item";
import { IntentChoice } from "@/design-system/components/intent-choice";
import { IntentStrip } from "@/design-system/components/intent-strip";
import { KbDocumentText } from "@/design-system/components/kb-document-text";
import { StaffNote } from "@/design-system/components/staff-note";
import { Tag } from "@/design-system/components/tag";
import { WarningList } from "@/design-system/components/warning-list";
import { renderUi } from "@/test/render-app";

describe("ConfidenceMeter", () => {
  it.each([
    ["high", 0.91, "Confidence High · 91%"],
    ["medium", 0.64, "Confidence Medium · 64%"],
    ["low", 0.41, "Confidence Low · 41%"],
  ] as const)("says the %s band and the percentage", (band, probability, text) => {
    renderUi(<ConfidenceMeter band={band} probability={probability} />);

    expect(screen.getByText(/Confidence/).parentElement).toHaveTextContent(text);
  });
});

describe("Tag", () => {
  it("shows its label", () => {
    renderUi(<Tag tone="ai">AI suggestion</Tag>);

    expect(screen.getByText("AI suggestion")).toBeVisible();
  });
});

describe("InboxItem", () => {
  it("links to the ticket and shows its facts, its details, and who opened it", () => {
    renderUi(
      <ul>
        <InboxItem
          to="/console/tickets/TCK-1042"
          ticketId="TCK-1042"
          createdAt="2026-11-05T08:42:00Z"
          customerName="Linh Tran"
          excerpt="Where is my refund?"
          openedAt="2026-11-05T08:56:00Z"
        >
          Refund status
        </InboxItem>
      </ul>,
    );

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/console/tickets/TCK-1042");
    expect(link).toHaveTextContent(
      "TCK-104218 minutes agoLinh TranWhere is my refund?Refund statusOpened 4 minutes ago",
    );
  });

  it("leaves out the opening line until a person opened the ticket", () => {
    renderUi(
      <ul>
        <InboxItem
          to="/console/tickets/TCK-1"
          ticketId="TCK-1"
          createdAt="2026-11-05T08:42:00Z"
          customerName="An Vo"
          excerpt="Hello"
        >
          No analysis
        </InboxItem>
      </ul>,
    );

    expect(screen.queryByText(/Opened/)).not.toBeInTheDocument();
  });
});

describe("IntentStrip", () => {
  it("shows a predicted intent with its confidence and the next candidates", () => {
    renderUi(
      <IntentStrip
        intentName="Refund status"
        confidence={{ band: "high", probability: 0.91 }}
        candidates={[{ name: "Request refund", probability: 0.05 }]}
      />,
    );

    const strip = screen.getByRole("region", { name: "Intent" });
    expect(strip).toHaveTextContent("Refund statusConfidence High · 91%Predicted");
    expect(strip).toHaveTextContent("Next candidates:Request refund 5%");
  });

  it("marks an intent that staff chose, without a confidence or candidates", () => {
    renderUi(<IntentStrip intentName="Request refund" candidates={[]} />);

    const strip = screen.getByRole("region", { name: "Intent" });
    expect(within(strip).getByText("Chosen by staff")).toBeVisible();
    expect(strip).not.toHaveTextContent("Confidence");
    expect(strip).not.toHaveTextContent("Next candidates");
  });
});

describe("IntentChoice", () => {
  it("lists the candidates with the confidence of the predicted one (UI-42)", () => {
    renderUi(
      <IntentChoice
        candidates={[
          { name: "Cancel order", probability: 0.41, band: "low" },
          { name: "Change order", probability: 0.33 },
        ]}
      />,
    );

    const items = within(screen.getByRole("region", { name: "Choose an intent" })).getAllByRole(
      "listitem",
    );
    expect(items.map((item) => item.textContent)).toEqual([
      "Cancel orderConfidence Low · 41%",
      "Change order33%",
    ]);
  });
});

describe("WarningList", () => {
  const warning = { warningId: "w1", title: "Missing information", description: "Check it." };

  it.each([
    ["one warning", [warning], "1 warning to check before sending"],
    [
      "two warnings",
      [warning, { ...warning, warningId: "w2" }],
      "2 warnings to check before sending",
    ],
  ])("counts %s", (_case, warnings, text) => {
    renderUi(<WarningList warnings={warnings} />);

    expect(screen.getByText(text)).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(warnings.length);
  });
});

describe("DraftText", () => {
  it("shows paragraphs of segments as plain text (SEC-22)", () => {
    renderUi(
      <DraftText
        paragraphs={[
          { paragraphId: "p0", segments: [{ segmentId: "s1", text: "<b>Hello</b>" }] },
          {
            paragraphId: "p1",
            segments: [
              { segmentId: "s2", text: "One." },
              { segmentId: "s3", text: "Two.", markers: <span>[1]</span> },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByText("<b>Hello</b>")).toBeVisible();
    expect(screen.getByText(/One\. Two\./)).toHaveTextContent("One. Two.[1]");
  });
});

describe("StaffNote and KbDocumentText", () => {
  it("shows the staff note as text", () => {
    renderUi(<StaffNote>{"<i>For staff</i>"}</StaffNote>);

    expect(screen.getByText("<i>For staff</i>")).toBeVisible();
  });

  it("highlights the passage in the full text", () => {
    renderUi(<KbDocumentText body="Before. The passage. After." highlight="The passage." />);

    expect(screen.getByText("The passage.").tagName).toBe("MARK");
  });

  it("highlights nothing without a passage", () => {
    renderUi(<KbDocumentText body="Before. After." />);

    expect(screen.getByText("Before. After.").tagName).toBe("P");
  });

  it.each([
    ["an empty passage", ""],
    ["a passage that the text does not hold", "Missing."],
  ])("highlights nothing for %s", (_case, highlight) => {
    renderUi(<KbDocumentText body="Before. After." highlight={highlight} />);

    expect(screen.getByText("Before. After.").tagName).toBe("P");
  });
});
