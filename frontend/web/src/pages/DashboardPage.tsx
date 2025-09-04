import React from 'react';
import ChatBox from '../components/ChatBox';

const DashboardPage: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-secondary-800 text-white font-sans">
      <ChatBox />
    </div>
  );
};

export default DashboardPage;