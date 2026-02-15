import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { AnimatedSelector, type SelectorOption } from "..";

const options: SelectorOption[] = [
  { id: "neutral", label: "Neutral" },
  { id: "cool", label: "Cool" },
  { id: "warm", label: "Warm" }
];

function SelectorDemo() {
  const [value, setValue] = useState<string | null>("cool");
  return (
    <AnimatedSelector
      name="theme"
      options={options}
      value={value}
      onChange={setValue}
      className="bg-column px-2"
    />
  );
}

const meta: Meta<typeof AnimatedSelector> = {
  title: "UI/AnimatedSelector",
  component: AnimatedSelector,
  render: () => <SelectorDemo />
};

export default meta;
type Story = StoryObj<typeof AnimatedSelector>;

export const Default: Story = {};
