from json import load, loads
from time import time, sleep
from typing import List, Set, Dict, Tuple, Optional, Any, Optional, cast
from uuid import uuid4
from threading import Thread, Timer

from channels.generic.websocket import WebsocketConsumer
from .settings import LOG, CONFIG


class Exchange:
    '''Basic exchange'''

    def __init__(self) -> None:
        self.initial_balance_value: float = 1.0
        self.strategy_check_timer_value: int = 10

        self.active_accounts: List[ExchangeAccount]
        self.coins: List[Strategy]
        self.name: str

        # list of all orders on exchange
        self.orders: list = []

    def ingest_strategy(self, strategy: Strategy) -> None:
        '''Ingests strategies to exchange forming default symbols'''

        # if we have BTC/USD = 6500, meaning that 1 BTC is
        # equivalent to 6500 USD, then base_asset is BTC and
        # quote asset is USD
        base_asset, quote_asset = strategy.symbol.split('_')

        LOG.info('Ingesting {} strategy to {} exchange'.format(
            base_asset, self.name
        ))

        self.coins.append(strategy)

        # set status for testing
        strategy.status = 'READY'

        # schedule strategy checl procedures
        self._async_strategy_check(strategy)

    def _async_strategy_check(self, strategy: Strategy) -> None:
        '''Starts thread for strategy check'''

        thread: Thread = Thread(
            target=self._handle_strategy, args=(strategy,)
        )
        thread.start()

    def _handle_strategy(self, strategy: Strategy) -> None:
        '''Checks strategy conditions every fixed period of time'''

        while True:
            sleep(self.strategy_check_timer_value)
            strategy.check_conditions()

    def accept_account(self, api_key: str) -> None:
        '''Accepts api key and creates exchange account info'''

        if api_key not in self.active_accounts:
            # create account info template
            account_data: dict = {
                'balance': {
                    'available': {},
                    'frozen': {}
                }
            }

            # fill account balance
            for coin in self.assets:
                account_data['balance']['available'].update({
                    coin: self.initial_balance_value
                })

                account_data['balance']['frozen'].update({
                    coin: 0.0
                })

            self.active_accounts.update({
                api_key: account_data
            })

            LOG.info('Api key {} successfully accepted'.format(api_key))

    def create_order(
        self,
        api_key: str,
        base_asset: str,
        quote_asset: str,
        amount: float,
        order_type: str,
    ) -> dict:
        '''
            Performs buy action with corresponding
            changes in balances and orders
        '''

        # create order
        order: Any = Order(
            api_key,
            amount,
            base_asset,
            quote_asset,
            order_type,
            self.coins
        )
        self.orders.append(order)

        # alter balances
        balance: Dict[str, Dict[
            str, float
        ]] = self.active_accounts[api_key]['balance']
        if order_type == 'BUY':
            balance['available'][quote_asset] -= order.price * order.amount
            balance['frozen'][quote_asset] += order.price * order.amount

        elif order_type == 'SELL':
            balance['available'][base_asset] -= order.amount
            balance['frozen'][base_asset] += order.amount

        LOG.info('Balances altered for api key {} due to order {}: {}'.format(
            api_key,
            order.id,
            self.active_accounts[api_key]['balance']
        ))

        handle_order_close: Timer = Timer(
            order.order_fill_delay + 1,
            self._handle_order_close,
            [order]
        )
        handle_order_close.start()

    def current_time(self, mode: str ='secs') -> int:
        '''Provides current time'''

        current_time: int = int(round(time()))

        if mode == 'millis':
            return current_time * 1000

        else:
            return current_time

    def _handle_order_close(self, order: Any) -> None:
        '''Alters balances when order is closed'''

        # find proper strategy
        strategy: Any = [
            strategy for strategy in self.coins
            if strategy.symbol == order.symbol
        ][0]

        order_traded_total_amount = sum(
            [trade.amount for trade in order.trades])
        order_traded_total = sum(
            [trade.amount * trade.price for trade in order.trades])

        order_original_total_amount = order.amount
        order_original_total = order.amount * order.price

        balance: Dict[str, Dict[
            str, float
        ]] = self.active_accounts[api_key]['balance']
        if order.order_type == 'BUY':
            balance['available'][order.base_asset] += order_traded_total_amount
            balance['frozen'][order.quote_asset] -= order_original_total

            strategy.buys += 1

        elif order.order_type == 'SELL':
            balance['frozen'][order.base_asset] -= order_original_total_amount
            balance['available'][order.quote_asset] += order_traded_total

            strategy.sells += 1


class Ticker:
    '''ticker logic which represents current strategy ticker state'''

    def __init__(
        self,
        values: List[float],
        is_infinite: bool,
        condition_start: Tuple[int],
        condition_stop: Tuple[int]
    ) -> None:
        self.values: List[float] = values
        self.is_infinite: bool = is_infinite
        self.is_triggered: bool = False
        self.counter: int = 0
        self.incrementor: Optional[Thread] = None
        self.condition_start: Tuple[int] = condition_start

    def check_conditions(self) -> None:
        '''check conditions to start ticker'''
        self._trigger()

    def _trigger(self, speed: int = 1) -> None:
        '''triggers counter with speed = counts/second'''

        # start async counter increment
        self.incrementor = Thread(
            target=self._increment_counter,
            args=(speed,)
        )
        self.incrementor.start()

        # indicate ticker is triggered
        self.is_triggered = not self.is_triggered

    def reset_counter(self) -> None:
        '''resets counter'''
        self.counter = 0

    def _increment_counter(self, speed: int) -> None:
        '''increments tickers counter'''

        wait_time: float = 1 / speed
        while True:
            sleep(wait_time)
            self.counter += 1

            # control counter
            if self.counter == len(self.values) - 1:
                if self.is_infinite:
                    self.reset_counter


class StrategyStatus:
    '''Status for strategy'''

    def __init__(self, value: str) -> None:
        self._value: str = value
        self.last_set: int = self._current_time()

    def __repr__(self) -> str:
        return 'Status value: \'{}\'. Set at: {}'.format(
            self.value,
            self.last_set
        )

    def _current_time(self) -> int:
        return int(round(time() * 1000))

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        self.last_set = self._current_time()
        self._value = value


class Strategy:
    '''Testing strategy'''

    def __init__(
        self,
        name: str,
        description: str,
        ticker: Ticker,
        symbol: str
    ) -> None:

        # model fields
        self.name: str = name
        self.ticker: Ticker = ticker
        self.description: str = description
        self.symbol: str = symbol
        self.status: StrategyStatus = StrategyStatus('INITIALIZED')

        # strategy session fields
        self.buys: int = 0
        self.sells: int = 0

    def _parse_params_from_query_set(self, query_set: Any) -> None:
        params: CoinParams = query_set

        self.ticker = loads(params.ticker)
        self.name = params.name
        self.description = params.description
        self.trigger = loads(params.trigger)
        self.stop_trigger = loads(params.stop_trigger)
        self.request_payload = loads(params.request_payload)
        self.symbol = params.currency_pair

        # reset counter when parsing new strategy params
        self.reset_counter()

    def check_conditions(self) -> None:

        if self.is_infinite:
            if not self.is_triggered:
                self.is_triggered = True
                LOG.info(
                    'Infinite strategy' +
                    ' "{}" has been triggered'.format(self.name)
                )
                self.status = 'INFINITE_LOOP'

        if self.is_triggered:

            if self.counter == len(self.ticker['ticker']) - 1:

                if not self.is_infinite:
                    self._check_success()

                else:
                    # reset infinite strategy
                    self._increment_counter()

            else:
                self._increment_counter()

        else:

            if self.counter == 0:

                if (self.buys == self.trigger['buys'] and
                        self.sells == self.trigger['sells']):
                    LOG.info(
                        'Coin "{}" has been triggered.'.format(self.name)
                    )
                    self.is_triggered = True
                    self.status = 'PRICE_CHANGE_TRIGGERED'

    def _check_success(self) -> None:

        if (self.buys == self.stop_trigger['buys'] and
                self.sells == self.stop_trigger['sells']):
            LOG.info('Coin "{}" has succeeded'.format(self.name))
            self.is_triggered = False
            self.status = 'SUCCEEDED'

        else:
            LOG.warning(
                'Coin "{}" has failed to succeed'.format(self.name))
            self.is_triggered = False
            self.status = 'FAILED'

    def _increment_counter(self) -> None:
        if self.counter < len(self.ticker['ticker']) - 1:
            self.counter += 1

        elif (self.counter == len(self.ticker['ticker']) - 1 and
                self.is_infinite):
            self.reset_counter()

    def reset_counter(self) -> None:
        self.counter = 0


class Deal:
    '''Basic deal'''

    def __init__(
        self,
        api_key: str,
        amount: float,
        price: float,
        base_asset: str,
        quote_asset: str,
        deal_type: str
    ) -> None:

        self.api_key: str = api_key
        self.amount: float = amount
        self.price: float = price
        self.base_asset: str = base_asset
        self.quote_asset: str = quote_asset
        self.deal_type: str = deal_type


class Order(Deal):
    '''Implements basic order functionality'''

    def __init__(
        self,
        api_key: str,
        amount: float,
        base_asset: str,
        quote_asset: str,
        order_type: str,
        context: list,
        random_fill: bool = True
    ):
        super().__init__()
        self.id: str = str(uuid4())
        self.api_key: str = api_key
        self.amount: float = amount
        self.base_asset: str = base_asset
        self.quote_asset: str = quote_asset
        self.order_type: str = order_type
        self.created: int = int(round(time()))
        self.status: str = 'OPEN'
        self.trades: list = list()
        self.context: list = context
        self.symbol: str = ''.join([self.base_asset, '_', self.quote_asset])

        self.price: float = self._get_original_price()

        # timers for trades
        self.trade_timers: list = list()

        # set time when order will be fully filled
        self.order_fill_delay: int = 15

        # number of trades
        self.number_of_trades: int = 1

        # define what amount will be filled with trades
        # and what amount will be left unfilled
        self.fill_percent: float = 1.0

        if random_fill:
            self._compute_fill_properties()

        # TODO make it random
        # what amount will be traded per trade
        self.trade_amount: float = (
            (self.amount * self.fill_percent) / self.number_of_trades
        )

        self.trade_delay_step: float = (
            self.order_fill_delay / self.number_of_trades
        )

        for i in range(self.number_of_trades):
            # current delay for trade timer
            current_trade_delay = (
                self.trade_delay_step + i * self.trade_delay_step
            )

            # generate trade
            current_trade = Trade(
                self.id,
                self.trade_amount,
                self.base_asset,
                self.quote_asset,
                self.order_type,
                self.context
            )

            # start trade timer
            current_trade_timer = Timer(
                current_trade_delay,
                self._handle_trade,
                [current_trade]
            )
            current_trade_timer.start()

            self.trade_timers.append(current_trade_timer)

        LOG.info(
            '{} order for {} with id {} for api key {} created'.format(
                self.order_type,
                ''.join([self.base_asset, '_', self.quote_asset]),
                self.id,
                self.api_key
            )
        )

    def cancel(self) -> None:
        '''Cancels current order'''

        # cancel all trade timers
        for timer in self.trade_timers:
            timer.cancel()

        self.status = 'CANCELED'

        LOG.info(
            '{} order for {} with id {} canceled'.format(
                self.order_type,
                ''.join([self.base_asset, '_', self.quote_asset]),
                self.id
            )
        )

    def _handle_trade(self, trade: Any) -> None:
        '''Handles trade routine for order'''

        self.trades.append(trade)
        self._check_close()

    def _check_close(self) -> None:
        '''Checks condition for order close and closes it'''

        if len(self.trades) == self.number_of_trades:
            self.status = 'FILLED'

            LOG.info(
                '{} order for {} with id {} closed'.format(
                    self.order_type,
                    ''.join([self.base_asset, '_', self.quote_asset]),
                    self.id
                )
            )

    def _compute_fill_properties(self) -> None:
        self.number_of_trades = int(ceil(random() * 5))
        self.fill_percent = 1 - random() * 0.03

    def _get_original_price(self) -> float:
        '''Gets the symbol rate in moment of order creation '''

        strategy: Any = [
            strategy for strategy in self.context
            if strategy.symbol == self.symbol
        ][0]
        price: float = float(strategy.ticker['ticker'][strategy.counter])
        return price


class Trade(Deal):
    '''Implements basic trade functionality'''

    def __init__(
        self,
        order_id: str,
        amount: float,
        base_asset: str,
        quote_asset: str,
        trade_type: str,
        context: list
    ):
        super().__init__()
        self.order_id: str = order_id
        self.id: str = str(uuid4())
        self.created: int = int(round(time()))
        self.amount: float = amount
        self.base_asset: str = base_asset
        self.quote_asset: str = quote_asset
        self.context: list = context
        self.trade_type: str = trade_type
        self.symbol: str = ''.join([self.base_asset, '_', self.quote_asset])

        self.price: float = self._get_price()

    def _get_price(self) -> float:
        '''Gets the symbol rate in moment of trade creation '''

        strategy: Any = [
            strategy for strategy in self.context
            if strategy.symbol == self.symbol
        ][0]
        price: float = float(strategy.ticker['ticker'][strategy.counter])
        return price


class ExchangeAccount(object):
    '''basic exchange account'''

    def __init__(
        self,
        api_key: str,
        balance: Balance
    ) -> None:

        self.api_key: str = api_key
        self.balance: Balance = balance


class Balance(object):
    '''basic balance'''

    def __init__(self, symbol: str, available: float, reserved: float) -> None:
        self.symbol: str = symbol
        self.available: float = available
        self.reserved: float = reserved

        # keeps reserved by order amount of balance coin
        self.order_impacts: List[OrderImpact] = []

    def handle_order(self, order: Order) -> None:
        '''alters balance corresponding to order params'''

        if order.status == 'OPEN':
            reserved_amount = self._count_reserved_amount()
            # TODO balance reservation
            order_impact = OrderImpact(order.id, reserved_amount)
            self.order_impacts.append(order_impact)

        # TODO CLOSE status case

    # TODO
    def _count_reserved_amount(self) -> float:
        return 0.0


class OrderImpact:
    '''object for order book records'''

    def __init__(self, order_id: str, reserved_amount: float) -> None:
        self.order_id: str = order_id
        self.reserved_amount: float = reserved_amount


# TODO excample: BinanceSocketHandler


class Socket(WebsocketConsumer):
    '''docstring for Socket'''

    def __init__(self) -> None:
        super(Socket, self).__init__()


# class BinanceSocketHandler(WebsocketConsumer):
#     def __init__(self) -> None:
#         super().__init__()
#         self.stream_mode: str = None
#         self.binance: 'BinanceMock' = SESSION.exchange
#         self.current_ls: str = None

#         # put socket to SESSION
#         SESSION.accept_binance_socket(self)

#     def connect(self) -> None:

#         if len(self.scope['query_string']):
#             query_raw: str = str(self.scope['query_string'])
#             res: Any = re.search(r'(?P<mode>)kline|depth|ticker', query_raw)
#             self.stream_mode = res.group()

#         else:
#             current_ls_or_ticker: str = self.scope['path'].split('/')[-1]

#             if current_ls_or_ticker == '!ticker@arr':
#                 self.stream_mode = 'ticker'

#             else:
#                 self.stream_mode = 'account'
#                 self.current_ls = current_ls_or_ticker

#         self.accept()

#         LOG.info(
#             'Accepted Binance socket connection to' +
#             ' channel {} with listenkey {}'.format(
#                 self.stream_mode,
#                 self.current_ls
#             )
#         )

#         thread_sender: Thread = Thread(
#             target=self.dispatch_data)
#         thread_sender.start()

#     def disconnect(self, close_code: Any) -> None:
#         pass

#     def receive(self, text_data: Any) -> None:
#         pass

#     def dispatch_data(self) -> None:
#         if self.stream_mode == 'depth':
#             delta_size: float = 0.4

#             while True:
#                 sign: int = numpy.power(
#                     -1,
#                     numpy.round((numpy.random.random() * 2))
#                 )
#                 delta: float = numpy.random.random() * delta_size
#                 sleep_diff: float = sign * delta
#                 sleep(1 + sleep_diff)

#                 for (index, strategy) in enumerate(self.binance.strategies):
#                     data: int = self.binance.prepare_order_book_info(index)

#                     self.handle_send(data)

#         elif self.stream_mode == 'kline':
#             self.send(text_data=dumps(self.stream_mode))

#         elif self.stream_mode == 'ticker':
#             delta_size: float = 0.4

#             while True:
#                 sign: int = numpy.power(
#                     -1,
#                     numpy.round((numpy.random.random() * 2))
#                 )
#                 delta: float = numpy.random.random() * delta_size
#                 sleep_diff: float = sign * delta
#                 sleep(1 + sleep_diff)

#                 data: list = self.binance.prepare_ticker()
#                 self.handle_send(data)

#         elif self.stream_mode == 'account':
#             # listen key routine
#             sockets: dict = SESSION.exchange.account_socket_channels
#             api_key: str = next(
#                 (
#                     api_key for (index, api_key) in enumerate(sockets) if (
#                         self.current_ls in sockets[api_key].values()
#                     )
#                 ),
#                 None
#             )

#             if api_key:
#                 sockets[api_key]['socket'] = self

#                 LOG.info(
#                     'Socket opened for apikey' +
#                     ' {} with listenkey {}'.format(
#                         api_key, self.current_ls
#                     )
#                 )
#             else:
#                 self.close(1000)

#                 LOG.info(
#                     'Socket closed for listenkey' +
#                     ' {} due to listenkey not found'.format(
#                         self.current_ls
#                     )
#                 )

#     def handle_send(self, data: Any) -> None:
#         try:
#             if self.stream_mode == 'ticker':
#                 LOG.info(
#                     'Following data has been sent' +
#                     ' to ticker socket: {}'.format(data))
#                 self.send(text_data=dumps(data))

#             else:
#                 LOG.info(
#                     'Following data has' +
#                     ' been sent to socket {}: {}'.format(
#                         self.current_ls, data
#                     )
#                 )
#                 self.send(text_data=dumps(data))

#         except Exception as err:
#             LOG.error(
#                 'Sending data has failed with' +
#                 ' the following error: {}'.format(str(err)))
#             self.close(1000)
