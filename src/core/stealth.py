from playwright.sync_api import Page

class StealthConfig:
    # 隐身配置 - 反检测策略
    
    @staticmethod
    def apply(page: Page):
        # 应用反检测脚本
        page.add_init_script('''
            // 覆盖navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 覆盖chrome对象
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 覆盖permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 覆盖plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 覆盖languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 覆盖webgl
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
            
            // 覆盖notification
            const originalNotification = window.Notification;
            window.Notification = function(title, options) {
                if (arguments.length === 0) {
                    return originalNotification;
                }
                return new originalNotification(title, options);
            };
            window.Notification.permission = originalNotification.permission;
            window.Notification.requestPermission = originalNotification.requestPermission.bind(originalNotification);
        ''')
    
    @staticmethod
    def setup_route_interception(page: Page):
        # 设置请求拦截
        def handle_route(route, request):
            headers = request.headers
            
            # 修改User-Agent
            headers['user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            
            # 添加Accept-Language
            headers['accept-language'] = 'zh-CN,zh;q=0.9,en;q=0.8'
            
            # 添加Referer
            if 'referer' not in headers:
                headers['referer'] = request.url
            
            route.continue_(headers=headers)
        
        page.route("**/*", handle_route)
    
    @staticmethod
    def block_resources(page: Page, resource_types: list = None):
        # 拦截不需要的资源
        if resource_types is None:
            resource_types = ['image', 'font', 'media']
        
        def handler(route, request):
            if request.resource_type in resource_types:
                route.abort()
            else:
                route.continue_()
        
        page.route("**/*", handler)
