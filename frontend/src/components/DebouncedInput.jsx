import { useEffect, useState } from 'react'

/**
 * Text input that waits until the user stops typing (300 ms) before calling
 * onCommit(value). Typing stays instant; the API is called far less often.
 *
 * If the `value` prop changes from the outside (Clear filters, browser back
 * button) the draft is reset to match it.
 */
function DebouncedInput({ value, onCommit, delay = 300, ...inputProps }) {
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)

  // "Adjusting state when a prop changes" - the pattern recommended by the
  // React docs instead of a setState inside useEffect.
  if (value !== lastValue) {
    setLastValue(value)
    setDraft(value)
  }

  useEffect(() => {
    if (draft === value) return undefined
    const handle = setTimeout(() => onCommit(draft), delay)
    return () => clearTimeout(handle)
  }, [draft, value, delay, onCommit])

  return <input {...inputProps} value={draft} onChange={(e) => setDraft(e.target.value)} />
}

export default DebouncedInput
