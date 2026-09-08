export type Message = {
  role: "you" | "dux";
  text: string;
};

export type StepEvent = {
  type: "step";
  node: string;
};

export type TokenEvent = {
  type: "token";
  text: string;
};

export type StreamEvent = StepEvent | TokenEvent;
