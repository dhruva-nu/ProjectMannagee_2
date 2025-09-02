import { useState } from 'react'
import ChatBox from './components/ChatBox'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-secondary-800 text-white p-8 font-sans">
      <div className="flex space-x-4 mb-8">
        <a href="https://vite.dev" target="_blank" rel="noopener noreferrer">
          <img src={viteLogo} className="h-24 w-24 p-4 transition-filter duration-300 hover:drop-shadow-[0_0_2em_#646cffaa]" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank" rel="noopener noreferrer">
          <img src={reactLogo} className="h-24 w-24 p-4 transition-filter duration-300 hover:drop-shadow-[0_0_2em_#61dafbaa]" alt="React logo" />
        </a>
      </div>
      <h1 className="text-5xl font-bold mb-8 text-primary-500">Vite + React</h1>
      <div className="p-8 rounded-lg shadow-lg bg-secondary-700 text-center mb-8">
        <button
          className="btn bg-primary-600 hover:bg-primary-500 text-white text-shadow-[0_0_8px_var(--color-primary-400)] shadow-[0_0_12px_var(--color-primary-500)] hover:shadow-[0_0_20px_var(--color-primary-400)] px-4 py-2 rounded-lg transition-all"
          onClick={() => setCount((count) => count + 1)}
        >
          count is {count}
        </button>
        <p className="mt-4 text-lg text-gray-300">
          Edit <code>src/App.tsx</code> and save to test HMR
        </p>
      </div>
      <p className="text-gray-500 text-sm">
        Click on the Vite and React logos to learn more
      </p>
      {/* Right-aligned chat widget */}
      <ChatBox />
    </div>
  )
}

export default App
