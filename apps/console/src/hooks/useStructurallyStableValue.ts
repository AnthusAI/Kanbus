import { useRef } from "react";

export function useStructurallyStableValue<Value>(value: Value): Value {
  const retainedValueRef = useRef<{ value: Value; serialized: string } | null>(null);
  const serialized = JSON.stringify(value);
  if (retainedValueRef.current === null || retainedValueRef.current.serialized !== serialized) {
    retainedValueRef.current = { value, serialized };
  }
  return retainedValueRef.current.value;
}
