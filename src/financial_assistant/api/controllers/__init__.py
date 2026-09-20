from . import (
    anomaly_controller,
    investigation_controller,
    market_controller,
    news_controller,
    portfolio_controller,
    story_controller,
    system_controller,
)

ROUTERS = (
    system_controller.router,
    portfolio_controller.router,
    market_controller.router,
    anomaly_controller.router,
    news_controller.router,
    investigation_controller.router,
    story_controller.router,
)
