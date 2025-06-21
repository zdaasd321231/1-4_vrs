import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
// Импортируем noVNC напрямую
import RFB from 'novnc/core/rfb';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VncViewer = ({ connection, onClose }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [rfb, setRfb] = useState(null);
  const vncRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (connection) {
      initializeVncConnection();
    }

    return () => {
      if (rfb) {
        rfb.disconnect();
      }
    };
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

      // Создаем WebSocket URL для VNC подключения
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = window.location.port ? `:${window.location.port}` : '';
      
      // Используем прямое VNC подключение через websockify
      const vncUrl = `${protocol}//${host}${port}/websockify?token=${connection.id}`;
      
      console.log('Connecting to VNC:', vncUrl);
      
      // Очищаем контейнер
      if (vncRef.current) {
        vncRef.current.innerHTML = '';
      }
      
      // Создаем noVNC RFB объект
      const rfbConnection = new RFB(vncRef.current, vncUrl, {
        credentials: {
          password: connection.vnc_password || 'vnc123pass'
        }
      });

      // Обработчики событий noVNC
      rfbConnection.addEventListener('connect', () => {
        console.log('VNC connected successfully');
        setIsConnected(true);
        setConnectionStatus('connected');
        setError(null);
      });

      rfbConnection.addEventListener('disconnect', (e) => {
        console.log('VNC disconnected:', e.detail);
        setIsConnected(false);
        setConnectionStatus('disconnected');
        if (e.detail.clean === false) {
          setError('Подключение к VNC серверу потеряно');
        }
      });

      rfbConnection.addEventListener('credentialsrequired', () => {
        console.log('VNC credentials required');
        setError('Требуется аутентификация VNC');
        setConnectionStatus('error');
      });

      rfbConnection.addEventListener('securityfailure', (e) => {
        console.log('VNC security failure:', e.detail);
        setError('Ошибка безопасности VNC: ' + e.detail.reason);
        setConnectionStatus('error');
      });

      setRfb(rfbConnection);
      
    } catch (err) {
      console.error('VNC connection error:', err);
      setError('Ошибка подключения к VNC: ' + err.message);
      setConnectionStatus('error');
    }
  };

  const sendCtrlAltDel = () => {
    if (rfb && isConnected) {
      rfb.sendCtrlAltDel();
    }
  };

  const sendKey = (keysym) => {
    if (rfb && isConnected) {
      rfb.sendKey(keysym);
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
    if (rfb) {
      rfb.disconnect();
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
              onClick={initializeVncConnection}
              className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 transition-colors"
            >
              🔄 Переподключить
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
        {isConnected && (
          <div className="p-2 border-b border-gray-200 bg-gray-50">
            <div className="flex space-x-2">
              <button
                onClick={() => sendKey(0xffe3)} // Left Ctrl
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Ctrl
              </button>
              <button
                onClick={() => sendKey(0xffe9)} // Left Alt
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Alt
              </button>
              <button
                onClick={() => sendKey(0xffff)} // Delete
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Del
              </button>
              <button
                onClick={() => sendKey(0xff09)} // Tab
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Tab
              </button>
              <button
                onClick={sendCtrlAltDel}
                className="px-3 py-1 bg-red-200 text-red-700 rounded text-sm hover:bg-red-300 transition-colors"
              >
                Ctrl+Alt+Del
              </button>
              <button
                onClick={() => sendKey(0xff1b)} // Escape
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Esc
              </button>
              <button
                onClick={() => sendKey(0xff0d)} // Enter
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors"
              >
                Enter
              </button>
            </div>
          </div>
        )}

        {/* Область VNC экрана */}
        <div className="flex-1 overflow-hidden bg-gray-900">
          {error && (
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

          {!error && connectionStatus === 'connecting' && (
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

          {/* Контейнер для noVNC */}
          <div 
            ref={vncRef}
            className="w-full h-full"
            style={{ 
              background: '#1a1a1a',
              display: error || connectionStatus === 'connecting' ? 'none' : 'block'
            }}
          />
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
              <span>Качество: {isConnected ? 'Высокое' : 'Н/Д'}</span>
              <span>Протокол: RFB/VNC</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VncViewer;