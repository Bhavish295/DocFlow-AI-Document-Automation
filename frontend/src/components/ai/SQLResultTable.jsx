import './SQLResultTable.css'

function formatCell(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
  return String(value)
}

function SQLResultTable({ columns = [], rows = [], emptyMessage = 'No rows returned.' }) {
  if (!columns.length || !rows.length) {
    return <div className="sql-result-table__empty">{emptyMessage}</div>
  }

  return (
    <div className="sql-result-table">
      <div className="sql-result-table__scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column.replace(/_/g, ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`row-${index}`}>
                {columns.map((column) => (
                  <td key={`${index}-${column}`}>{formatCell(row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default SQLResultTable
