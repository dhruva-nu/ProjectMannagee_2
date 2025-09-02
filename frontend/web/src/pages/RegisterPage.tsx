import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const RegisterPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const handleRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(''); // Clear previous messages

    try {
      const response = await fetch('http://localhost:8000/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message);
        console.log('Registration successful:', data);
        // Optionally redirect to login page after successful registration
        navigate('/login');
      } else {
        setMessage(data.detail || 'Registration failed');
        console.error('Registration failed:', data);
      }
    } catch (error) {
      setMessage('An error occurred. Please try again.');
      console.error('Network error or unexpected issue:', error);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-secondary-800 text-white font-sans">
      <h1 className="text-4xl font-bold mb-8 text-primary-500">Register</h1>
      <form onSubmit={handleRegister} className="flex flex-col gap-4 p-8 rounded-lg bg-secondary-700 shadow-lg w-80">
        <div className="flex flex-col">
          <label htmlFor="username" className="mb-1 text-sm text-gray-300">Username:</label>
          <input
            type="text"
            id="username"
            name="username"
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="flex flex-col">
          <label htmlFor="password" className="mb-1 text-sm text-gray-300">Password:</label>
          <input
            type="password"
            id="password"
            name="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button
          type="submit"
          className="btn bg-primary-600 hover:bg-primary-500 text-white text-shadow-[0_0_8px_var(--color-primary-400)] shadow-[0_0_12px_var(--color-primary-500)] hover:shadow-[0_0_20px_var(--color-primary-400)] px-4 py-2 rounded-lg transition-all mt-4"
        >
          Register
        </button>
        {message && <p className="mt-4 text-center text-sm">{message}</p>}
      </form>
      <p className="mt-8 text-sm text-gray-400">
        Already have an account? <Link to="/login" className="text-accent-cyan hover:underline">Login here</Link>
      </p>
    </div>
  );
};

export default RegisterPage;