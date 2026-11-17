/**
 * The density of a {@link Panel}, which its header and sections read: `comfortable` is the card of
 * the shop and admin designs, `compact` the console panel of 12 px by 16 px with 14 px headings
 * (console UI design, mockups).
 */
import { createContext } from "react";

/** How much room a panel gives its content. */
export type PanelDensity = "comfortable" | "compact";

/** The density of the nearest panel; `comfortable` outside a console panel. */
export const PanelDensityContext = createContext<PanelDensity>("comfortable");
