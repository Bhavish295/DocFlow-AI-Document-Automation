import './PlaceholderPage.css'

/**
 * Unused in the main nav after Step 28. Kept for optional future-scope pages only.
 */
function PlaceholderPage({ title, description }) {
  return (
    <div className="placeholder">
      <div className="placeholder__frame">
        <p className="placeholder__badge">Future scope</p>
        <h2 className="placeholder__title">{title}</h2>
        <p className="placeholder__copy">{description}</p>
        <p className="placeholder__note">
          This area is not part of the current submission build. Implemented modules
          are available from the sidebar.
        </p>
      </div>
    </div>
  )
}

export default PlaceholderPage
