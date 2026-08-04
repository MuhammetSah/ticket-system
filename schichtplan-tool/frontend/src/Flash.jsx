import { useEffect } from 'react'

function Flash({ flash, onClose }) {
  useEffect(() => {
    if (!flash) return
    const timer = setTimeout(() => {
      onClose()
    }, 4000)
    return () => clearTimeout(timer)
  }, [flash, onClose])

  if (!flash) return null

  return (
    <div className={`flash flash-${flash.type}`}>
      {flash.text}
    </div>
  )
}

export default Flash
