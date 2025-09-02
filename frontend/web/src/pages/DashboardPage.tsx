import React from 'react';
import ChatBox from '../components/ChatBox';

const DashboardPage: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-secondary-800 text-white p-8 font-sans">
      <h1 className="text-4xl font-bold mb-8 text-primary-500">Welcome to your Dashboard!</h1>
      <p className="text-lg text-gray-300 mb-8">You are successfully logged in.</p>
      <ChatBox />
    </div>
  );
};

export default DashboardPage;