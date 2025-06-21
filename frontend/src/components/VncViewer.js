import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VncViewer = ({ connection, onClose }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [screenshot, setScreenshot] = useState(null);
  const vncRef = useRef(null);
  const containerRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (connection) {
      initializeVncConnection();
      // Обновлять скриншот каждые 2 секунды для демонстрации
      const interval = setInterval(refreshScreenshot, 2000);
      return () => {
        clearInterval(interval);
        if (wsRef.current) {
          wsRef.current.close();
        }
      };
    }
  }, [connection]);

  const initializeVncConnection = async () => {
    try {
      setConnectionStatus('connecting');
      setError(null);
      
      if (!connection.ip_address) {
        setError('IP адрес не указан для данного соединения');
        setConnectionStatus('error');
        return;
      }

      // Создаем WebSocket подключение
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : '';
      
      const wsUrl = `${protocol}//${host}${port}/websockify?token=${connection.id}`;
      
      console.log('Connecting to VNC via WebSocket:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log('VNC WebSocket connected');
        setIsConnected(true);
        setConnectionStatus('connected');
        setError(null);
        refreshScreenshot();
      };
      
      ws.onmessage = (event) => {
        console.log('VNC data received:', event.data.length, 'bytes');
        // В реальной реализации здесь обработка VNC данных
      };
      
      ws.onclose = (event) => {
        console.log('VNC WebSocket disconnected:', event.code, event.reason);
        setIsConnected(false);
        setConnectionStatus('disconnected');
        if (event.code !== 1000) {
          setError('Подключение к VNC серверу потеряно: ' + event.reason);
        }
      };
      
      ws.onerror = (error) => {
        console.error('VNC WebSocket error:', error);
        setError('Ошибка WebSocket подключения');
        setConnectionStatus('error');
        // Показываем скриншот даже при ошибке WebSocket
        refreshScreenshot();
      };
      
      wsRef.current = ws;
      
    } catch (err) {
      console.error('VNC connection error:', err);
      setError('Ошибка подключения к VNC: ' + err.message);
      setConnectionStatus('error');
    }
  };

  const refreshScreenshot = async () => {
    try {
      const response = await axios.get(`${API}/vnc/${connection.id}/screenshot`, {
        responseType: 'blob'
      });
      
      const url = URL.createObjectURL(response.data);
      setScreenshot(url);
      
    } catch (err) {
      console.error('Screenshot error:', err);
    }
  };

  const sendKey = (key) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'key',
        key: key
      }));
    }
  };

  const handleMouseEvent = (event) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && vncRef.current) {
      const rect = vncRef.current.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      
      wsRef.current.send(JSON.stringify({
        type: 'mouse',
        x: Math.floor(x),
        y: Math.floor(y),
        button: event.button,
        action: event.type
      }));
    }
  };

  const toggleFullscreen = async () => {
    if (!document.fullscreenElement) {
      await containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      await document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const disconnect = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    onClose();
  };

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-600';
      case 'connecting': return 'text-yellow-600';
      case 'disconnected': return 'text-red-600';
      case 'error': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const getStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return '🟢 Подключен';
      case 'connecting': return '🟡 Подключение...';
      case 'disconnected': return '🔴 Отключен';
      case 'error': return '❌ Ошибка';
      default: return '⚪ Неизвестно';
    }
  };

  return (
    <div 
      ref={containerRef}
      className={`fixed inset-0 z-50 bg-black bg-opacity-90 flex items-center justify-center ${isFullscreen ? 'p-0' : 'p-4'}`}
    >
      <div className={`bg-white shadow-xl ${isFullscreen ? 'w-full h-full' : 'w-full max-w-7xl h-5/6 rounded-lg'} flex flex-col`}>
        {/* Заголовок */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center space-x-4">
            <h2 className="text-xl font-bold text-gray-900">
              🖥️ VNC: {connection.name}
            </h2>
            <div className={`text-sm font-medium ${getStatusColor()}`}>
              {getStatusText()}
            </div>
            <div className="text-sm text-gray-600">
              {connection.ip_address}:{connection.vnc_port || 5900}
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <button
              onClick={toggleFullscreen}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
            >
              {isFullscreen ? '📱 Окно' : '🖥️ Полный экран'}
            </button>
            <button
              onClick={refreshScreenshot}
              className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 transition-colors"
            >
              🔄 Обновить экран
            </button>
            <button
              onClick={disconnect}
              className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700 transition-colors"
            >
              ❌ Закрыть
            </button>
          </div>
        </div>

        {/* Панель управления */}
        <div className="p-2 border-b border-gray-200 bg-gray-50">
          <div className="flex space-x-2">
            <button
              onClick={() => sendKey('ctrl')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Ctrl
            </button>
            <button
              onClick={() => sendKey('alt')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Alt
            </button>
            <button
              onClick={() => sendKey('delete')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Del
            </button>
            <button
              onClick={() => sendKey('tab')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Tab
            </button>
            <button
              onClick={() => sendKey('ctrl+alt+delete')}
              className="px-3 py-1 bg-red-200 text-red-700 rounded text-sm hover:bg-red-300 transition-colors"
            >
              Ctrl+Alt+Del
            </button>
            <button
              onClick={() => sendKey('enter')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Enter
            </button>
            <button
              onClick={() => sendKey('escape')}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
            >
              Esc
            </button>
          </div>
        </div>

        {/* Область VNC экрана */}
        <div className="flex-1 overflow-hidden bg-gray-900">
          {error && !screenshot && (
            <div className="h-full flex items-center justify-center">
              <div className="text-center p-8">
                <div className="text-red-400 text-4xl mb-4">❌</div>
                <p className="text-red-400 text-lg mb-4">{error}</p>
                <button
                  onClick={initializeVncConnection}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                >
                  🔄 Попробовать снова
                </button>
              </div>
            </div>
          )}

          {!screenshot && connectionStatus === 'connecting' && (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-white mx-auto mb-4"></div>
                <p className="text-white text-lg">Подключение к VNC серверу...</p>
                <p className="text-gray-300 text-sm mt-2">
                  Подключение к {connection.ip_address}:{connection.vnc_port || 5900}
                </p>
              </div>
            </div>
          )}

          {/* VNC экран */}
          {screenshot && (
            <div className="w-full h-full flex items-center justify-center">
              <img
                ref={vncRef}
                src={screenshot}
                alt="VNC Screen"
                className="max-w-full max-h-full object-contain cursor-pointer"
                onClick={handleMouseEvent}
                onMouseDown={handleMouseEvent}
                onMouseUp={handleMouseEvent}
                onMouseMove={handleMouseEvent}
                draggable={false}
              />
            </div>
          )}
        </div>

        {/* Статус-бар */}
        <div className="p-2 border-t border-gray-200 bg-gray-50 text-sm text-gray-600">
          <div className="flex justify-between items-center">
            <div className="flex space-x-4">
              <span>Подключение: {connection.name}</span>
              <span>IP: {connection.ip_address}</span>
              <span>Порт: {connection.vnc_port || 5900}</span>
            </div>
            <div className="flex space-x-4">
              {isConnected && (
                <span className="text-green-600">🟢 Активное VNC соединение</span>
              )}
              <span>Качество: {isConnected ? 'Высокое' : 'Демо режим'}</span>
              <span>Протокол: WebSocket/VNC</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VncViewer;