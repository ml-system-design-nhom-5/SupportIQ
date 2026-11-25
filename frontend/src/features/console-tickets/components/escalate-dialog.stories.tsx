import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import {
  EscalateDialog,
  type EscalateDialogForm,
} from "@/features/console-tickets/components/escalate-dialog";

/** The form of the mockup: Missing case info and a note. */
const chosenForm: EscalateDialogForm = {
  reasonCodes: new Set(["missing_case_info"]),
  note: "The customer has no return tracking number.",
  onToggle: fn(),
  onNoteChange: fn(),
};

const meta = {
  title: "Console/TicketWorkspace/EscalateDialog",
  component: EscalateDialog,
  args: {
    ticketId: "TCK-1042",
    returnFocus: { opener: document.body, fallbackId: "escalate-ticket" },
    form: { ...chosenForm, reasonCodes: new Set(), note: "" },
    submission: { isPending: false, onSubmit: fn(), onCancel: fn() },
  },
} satisfies Meta<typeof EscalateDialog>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const ReasonChosen: Story = { args: { form: chosenForm } };
export const ReasonMissing: Story = {
  args: {
    form: {
      ...chosenForm,
      reasonCodes: new Set(),
      note: "",
      errors: { reasons: "Choose at least one reason." },
    },
  },
};
export const NoteMissing: Story = {
  args: {
    form: {
      ...chosenForm,
      reasonCodes: new Set(["other"]),
      note: "",
      errors: { note: "Write a note for the reason Other." },
    },
  },
};
export const Pending: Story = {
  args: { form: chosenForm, submission: { isPending: true, onSubmit: fn(), onCancel: fn() } },
};
export const Failure: Story = {
  args: {
    form: chosenForm,
    submission: {
      isPending: false,
      failure: {
        lead: "The ticket was not escalated.",
        message: "Something went wrong. Try again in a moment.",
        traceId: "319c0af7651916cd43dd8448eb211c80",
      },
      onSubmit: fn(),
      onCancel: fn(),
    },
  },
};
