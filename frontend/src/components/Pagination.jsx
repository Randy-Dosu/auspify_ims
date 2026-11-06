/**
 * Page controls + "Showing x–y of z" summary.
 *
 * Props: page, perPage, total, totalPages, onPageChange(page), onPerPageChange(n)
 */
const PER_PAGE_OPTIONS = [10, 20, 50, 100]

function Pagination({ page, perPage, total, totalPages, onPageChange, onPerPageChange }) {
  const first = total === 0 ? 0 : (page - 1) * perPage + 1
  const last = Math.min(page * perPage, total)

  return (
    <div className="pagination">
      <span className="muted">
        Showing {first}–{last} of {total}
      </span>
      <div className="pagination-controls">
        <label className="muted">
          Per page{' '}
          <select value={perPage} onChange={(e) => onPerPageChange(Number(e.target.value))}>
            {PER_PAGE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-small" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
          ‹ Previous
        </button>
        <span className="muted">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-small"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next ›
        </button>
      </div>
    </div>
  )
}

export default Pagination
