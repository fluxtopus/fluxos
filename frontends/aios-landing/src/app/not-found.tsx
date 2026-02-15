export default function NotFound() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'monospace', background: '#0b0d10', color: '#728c96', minHeight: '100vh' }}>
      <h2>404 - Not Found</h2>
      <p>The requested resource could not be located.</p>
      <a href="/" style={{ color: '#3b6e75', marginTop: '1rem', display: 'inline-block' }}>
        Return to base
      </a>
    </div>
  )
}
