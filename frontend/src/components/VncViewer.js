import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VncViewer = ({ connection, onClose }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [vncFrame, setVncFrame] = useState(null);
  const containerRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (connection) {
      initializeVncConnection();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
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

      // Используем noVNC через HTML5
      const vncUrl = `${connection.ip_address}:5800`; // HTTP порт TightVNC
      const vncPassword = connection.vnc_password || 'vnc123pass';
      
      console.log('Connecting to VNC HTTP interface:', vncUrl);
      
      // Создаем iframe для VNC веб-интерфейса TightVNC
      setVncFrame(`http://${vncUrl}/`);
      setIsConnected(true);
      setConnectionStatus('connected');
      
    } catch (err) {
      console.error('VNC connection error:', err);
      setError('Ошибка подключения к VNC: ' + err.message);
      setConnectionStatus('error');
    }
  };

  const connectWithNoVNC = () => {
    // Альтернативный способ - открыть VNC в новом окне
    const vncUrl = `http://${connection.ip_address}:5800/`;
    window.open(vncUrl, '_blank', 'width=1024,height=768,scrollbars=yes,resizable=yes');
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
              onClick={connectWithNoVNC}
              className="px-3 py-1 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 transition-colors"
            >
              🌐 Открыть в браузере
            </button>
            <button
              onClick={toggleFullscreen}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
            >
              {isFullscreen ? '📱 Окно' : '🖥️ Полный экран'}
            </button>
            <button
              onClick={disconnect}
              className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700 transition-colors"
            >
              ❌ Закрыть
            </button>
          </div>
        </div>

        {/* Информационная панель */}
        <div className="p-4 bg-blue-50 border-b border-gray-200">
          <div className="flex items-center space-x-4">
            <div className="text-sm">
              <strong>💡 Инструкции по подключению:</strong>
            </div>
          </div>
          <div className="mt-2 text-sm text-gray-700">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <strong>Способ 1:</strong> Нажмите "🌐 Открыть в браузере" для VNC через веб-интерфейс
              </div>
              <div>
                <strong>Способ 2:</strong> Используйте VNC клиент (адрес: {connection.ip_address}:5900, пароль: vnc123pass)
              </div>
            </div>
          </div>
        </div>

        {/* Область VNC экрана */}
        <div className="flex-1 overflow-hidden bg-gray-100">
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
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mx-auto mb-4"></div>
                <p className="text-gray-700 text-lg">Подключение к VNC серверу...</p>
                <p className="text-gray-500 text-sm mt-2">
                  Подключение к {connection.ip_address}:{connection.vnc_port || 5900}
                </p>
              </div>
            </div>
          )}

          {/* VNC iframe или инструкции */}
          {connectionStatus === 'connected' && (
            <div className="w-full h-full">
              {vncFrame ? (
                <iframe
                  src={vncFrame}
                  className="w-full h-full border-0"
                  title={`VNC ${connection.name}`}
                  onLoad={() => console.log('VNC iframe loaded')}
                  onError={() => setError('Не удалось загрузить VNC интерфейс')}
                />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center p-8 max-w-2xl">
                    <div className="text-6xl mb-6">🖥️</div>
                    <h3 className="text-2xl font-bold text-gray-900 mb-4">
                      VNC Подключение готово
                    </h3>
                    
                    <div className="bg-white p-6 rounded-lg shadow-md mb-6">
                      <h4 className="text-lg font-semibold mb-3">Параметры подключения:</h4>
                      <div className="space-y-2 text-left">
                        <div><strong>IP адрес:</strong> {connection.ip_address}</div>
                        <div><strong>VNC порт:</strong> {connection.vnc_port || 5900}</div>
                        <div><strong>HTTP порт:</strong> 5800</div>
                        <div><strong>Пароль:</strong> vnc123pass</div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <button
                        onClick={connectWithNoVNC}
                        className="w-full bg-green-600 text-white px-6 py-3 rounded-lg text-lg font-medium hover:bg-green-700 transition-colors"
                      >
                        🌐 Открыть VNC в браузере
                      </button>
                      
                      <div className="text-sm text-gray-600">
                        Или используйте любой VNC клиент с указанными параметрами
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Статус-бар */}
        <div className="p-3 border-t border-gray-200 bg-gray-50 text-sm text-gray-600">
          <div className="flex justify-between items-center">
            <div className="flex space-x-4">
              <span>📡 Подключение: {connection.name}</span>
              <span>🌐 IP: {connection.ip_address}</span>
              <span>🔌 Порт: {connection.vnc_port || 5900}</span>
            </div>
            <div className="flex space-x-4">
              <span>🔐 Пароль: vnc123pass</span>
              <span>📊 Протокол: VNC/RFB</span>
              {isConnected && (
                <span className="text-green-600">🟢 Готов к подключению</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VncViewer;