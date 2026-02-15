import type { Meta, StoryObj } from "@storybook/react";
import { Badge, Card, CardContent, CardHeader } from "..";

const meta: Meta<typeof Card> = {
  title: "UI/Card",
  component: Card,
  args: {
    children: (
      <>
        <CardHeader>
          <Badge>Kanbus</Badge>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <h3 className="text-lg font-semibold tracking-tight">
              Console card styling
            </h3>
            <p className="text-sm text-muted">
              Shared surface colors, typography, and rounded corners pulled from the
              Kanbus console theme.
            </p>
          </div>
        </CardContent>
      </>
    )
  }
};

export default meta;
type Story = StoryObj<typeof Card>;

export const Default: Story = {
  args: {
    className: "w-[360px]"
  }
};
