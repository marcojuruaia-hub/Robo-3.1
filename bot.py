#!/usr/bin/env python3
"""
ROBÔ GRID TRADING POLYMARKET - VERSÃO CORRIGIDA
Sem duplicação de ordens | Com gestão inteligente
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime

# ========== CONFIGURAÇÃO DE LOG ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========== CLASSE PRINCIPAL DO ROBÔ ==========
class PolymarketGridBot:
    def __init__(self, polymarket_client, config: Dict):
        """
        Inicializa o robô grid trading para Polymarket
        
        Args:
            polymarket_client: Seu cliente da API do Polymarket
            config: Configurações do grid
        """
        self.client = polymarket_client
        self.config = config
        
        # Grid de preços (0.80 até 0.52, decrementando 0.02)
        self.grid_prices = []
        self.setup_grid_prices()
        
        # Controle de ordens para evitar duplicação
        self.active_orders = {}  # {price: order_id}
        self.orders_history = []  # Histórico de ordens criadas
        
        # Status do robô
        self.is_running = False
        self.cycle_count = 0
        
        # Saldo cache
        self.last_balance = 0.0
        self.balance_update_time = 0
        
        logger.info("🤖 ROBÔ GRID TRADING INICIALIZADO")
        logger.info(f"📊 Grid: {len(self.grid_prices)} níveis (${self.grid_prices[0]:.2f} até ${self.grid_prices[-1]:.2f})")
    
    def setup_grid_prices(self):
        """Configura os preços do grid baseado na configuração"""
        start_price = self.config.get('max_price', 0.80)
        end_price = self.config.get('min_price', 0.52)
        step = self.config.get('step', 0.02)
        
        price = start_price
        while price >= end_price:
            self.grid_prices.append(round(price, 2))
            price -= step
        
        logger.info(f"🎯 Grid configurado: {self.grid_prices}")
    
    async def safe_api_call(self, func, *args, **kwargs):
        """Executa chamadas de API com tratamento de erro"""
        try:
            return await func(*args, **kwargs)
        except AttributeError as e:
            if '_get_headers' in str(e):
                logger.error("ERRO: Método _get_headers não encontrado")
                logger.error("Verifique a instalação da biblioteca do Polymarket")
                return None
            logger.error(f"Erro de atributo: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro na API: {e}")
            return None
    
    async def get_balance(self, force_update: bool = False) -> float:
        """
        Obtém o saldo da conta de forma segura
        
        Args:
            force_update: Força atualização mesmo se cache for recente
        """
        try:
            # Usa cache se for recente (menos de 30 segundos)
            if not force_update and time.time() - self.balance_update_time < 30:
                return self.last_balance
            
            # Tenta diferentes métodos comuns de API
            balance_methods = [
                'get_balance',
                'fetch_balance',
                'get_account_balance',
                'balance'
            ]
            
            for method_name in balance_methods:
                if hasattr(self.client, method_name):
                    try:
                        method = getattr(self.client, method_name)
                        result = await self.safe_api_call(method)
                        
                        if result is not None:
                            # Extrai o saldo dependendo do formato
                            if isinstance(result, dict) and 'free' in result:
                                balance = float(result['free'])
                            elif isinstance(result, dict) and 'balance' in result:
                                balance = float(result['balance'])
                            elif isinstance(result, (int, float, str)):
                                balance = float(result)
                            else:
                                continue
                            
                            self.last_balance = balance
                            self.balance_update_time = time.time()
                            return balance
                    except:
                        continue
            
            logger.warning("⚠️  Não foi possível obter saldo, usando último valor")
            return self.last_balance
            
        except Exception as e:
            logger.error(f"❌ Erro crítico ao obter saldo: {e}")
            return 0.0
    
    async def get_open_orders(self) -> List[Dict]:
        """Obtém todas as ordens abertas"""
        try:
            orders = await self.safe_api_call(self.client.get_open_orders)
            if orders is None:
                return []
            
            # Formata as ordens
            formatted_orders = []
            for order in orders:
                if isinstance(order, dict):
                    formatted_orders.append({
                        'id': order.get('id', ''),
                        'price': float(order.get('price', 0)),
                        'quantity': int(order.get('quantity', 0)),
                        'filled': int(order.get('filled', 0)),
                        'side': order.get('side', 'buy')
                    })
            
            return formatted_orders
            
        except Exception as e:
            logger.error(f"Erro ao obter ordens abertas: {e}")
            return []
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancela uma ordem específica"""
        try:
            result = await self.safe_api_call(self.client.cancel_order, order_id)
            if result:
                logger.info(f"🗑️  Ordem {order_id[:8]} cancelada")
                
                # Remove do controle interno
                for price, oid in list(self.active_orders.items()):
                    if oid == order_id:
                        del self.active_orders[price]
                        break
                
                return True
            return False
        except Exception as e:
            logger.error(f"Erro ao cancelar ordem: {e}")
            return False
    
    async def cancel_all_orders(self):
        """Cancela TODAS as ordens abertas"""
        logger.info("🔄 Cancelando TODAS as ordens abertas...")
        orders = await self.get_open_orders()
        
        if not orders:
            logger.info("✅ Nenhuma ordem para cancelar")
            return
        
        cancel_tasks = []
        for order in orders:
            cancel_tasks.append(self.cancel_order(order['id']))
        
        results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
        success_count = sum(1 for r in results if r is True)
        
        logger.info(f"✅ Canceladas {success_count}/{len(orders)} ordens")
        self.active_orders.clear()
    
    async def has_sufficient_balance(self, price: float, quantity: int = 5) -> bool:
        """
        Verifica se há saldo suficiente para uma ordem
        
        Args:
            price: Preço por share
            quantity: Quantidade de shares
        """
        try:
            balance = await self.get_balance()
            required = price * quantity
            
            # Adiciona 10% de margem para segurança
            required_with_margin = required * 1.1
            
            if balance >= required_with_margin:
                return True
            else:
                logger.debug(f"Saldo insuficiente: ${balance:.2f} < ${required_with_margin:.2f}")
                return False
                
        except Exception as e:
            logger.error(f"Erro na verificação de saldo: {e}")
            return False
    
    async def create_buy_order(self, price: float) -> bool:
        """
        Cria uma ordem de compra se não existir uma no mesmo preço
        
        Args:
            price: Preço da ordem
        """
        try:
            # 1. Verifica se já temos ordem neste preço
            if price in self.active_orders:
                logger.debug(f"⏭️  Já existe ordem ativa em ${price:.2f}")
                return False
            
            # 2. Verifica saldo
            quantity = self.config.get('quantity', 5)
            if not await self.has_sufficient_balance(price, quantity):
                logger.warning(f"💰 Saldo insuficiente para ordem a ${price:.2f}")
                return False
            
            # 3. Cria a ordem
            logger.info(f"🛒 Criando ordem: {quantity} shares a ${price:.2f}")
            
            order_result = await self.safe_api_call(
                self.client.create_order,
                side='buy',
                price=price,
                quantity=quantity,
                expiration='Until Cancelled'
            )
            
            if order_result and order_result.get('id'):
                order_id = order_result['id']
                
                # Registra no controle interno
                self.active_orders[price] = order_id
                self.orders_history.append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'price': price,
                    'quantity': quantity,
                    'id': order_id[:8]
                })
                
                logger.info(f"✅ COMPRA criada: {quantity} shares a ${price:.2f} (ID: {order_id[:8]})")
                return True
            else:
                logger.error(f"❌ Falha ao criar ordem em ${price:.2f}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar ordem: {e}")
            return False
    
    async def update_active_orders(self):
        """Atualiza a lista de ordens ativas baseado nas ordens abertas na API"""
        try:
            open_orders = await self.get_open_orders()
            current_prices = set()
            
            # Limpa ordens que não existem mais
            for price, order_id in list(self.active_orders.items()):
                found = False
                for order in open_orders:
                    if order['id'] == order_id:
                        found = True
                        current_prices.add(price)
                        break
                
                if not found:
                    logger.debug(f"Removendo ordem ${price:.2f} do controle interno")
                    del self.active_orders[price]
            
            # Adiciona novas ordens encontradas
            for order in open_orders:
                price = order['price']
                if price not in self.active_orders and order['side'] == 'buy':
                    self.active_orders[price] = order['id']
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar ordens ativas: {e}")
    
    async def cleanup_old_orders(self, max_age_minutes: int = 10):
        """
        Cancela ordens muito antigas que não foram executadas
        
        Args:
            max_age_minutes: Idade máxima em minutos
        """
        try:
            open_orders = await self.get_open_orders()
            current_time = time.time()
            
            for order in open_orders:
                # Tenta obter timestamp da ordem
                timestamp = order.get('timestamp', order.get('created_at', 0))
                if timestamp == 0:
                    continue
                
                order_age = (current_time - timestamp) / 60  # Em minutos
                
                if order_age > max_age_minutes:
                    logger.info(f"🕐 Ordem antiga ({order_age:.1f}min) em ${order['price']:.2f}")
                    await self.cancel_order(order['id'])
                    
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
    
    async def run_grid_cycle(self):
        """Executa um ciclo completo do grid trading"""
        self.cycle_count += 1
        
        # ========== CABEÇALHO DO CICLO ==========
        print(f"\n{'='*70}")
        print(f"🔄 CICLO {self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*70}")
        
        # 1. Atualiza saldo
        balance = await self.get_balance(force_update=True)
        print(f"💰 Saldo disponível: ${balance:.2f}")
        
        # 2. Atualiza ordens ativas
        await self.update_active_orders()
        open_orders = await self.get_open_orders()
        print(f"📊 Ordens abertas: {len(open_orders)}")
        
        # 3. Limpa ordens antigas
        await self.cleanup_old_orders()
        
        # 4. Executa grid de compras
        print("🔵 CRIANDO ORDENS DE COMPRA...")
        new_orders = 0
        
        for price in self.grid_prices:
            # Limite máximo de ordens simultâneas
            max_orders = self.config.get('max_concurrent_orders', 15)
            if len(self.active_orders) >= max_orders:
                print(f"⚠️  Limite de {max_orders} ordens atingido")
                break
            
            if await self.create_buy_order(price):
                new_orders += 1
                await asyncio.sleep(0.3)  # Pequena pausa entre ordens
        
        # 5. Resumo do ciclo
        print(f"\n📋 RESUMO DO CICLO {self.cycle_count}:")
        print(f"   • Ordens novas criadas: {new_orders}")
        print(f"   • Total ordens abertas: {len(open_orders)}")
        print(f"   • Saldo disponível: ${balance:.2f}")
        
        # 6. Histórico recente
        if self.orders_history[-5:]:
            print(f"\n📝 Últimas ordens criadas:")
            for order in self.orders_history[-5:]:
                print(f"   • {order['time']} - ${order['price']:.2f} (ID: {order['id']})")
        
        # 7. Aguarda próximo ciclo
        interval = self.config.get('interval', 20)
        print(f"\n⏳ Próximo ciclo em {interval} segundos...")
        print(f"{'='*70}")
    
    async def start(self):
        """Inicia o robô"""
        print("\n" + "="*70)
        print("🤖 ROBÔ GRID TRADING - POLYMARKET")
        print("="*70)
        print("🚀 INICIANDO OPERAÇÃO...")
        print(f"⏱️  Intervalo: {self.config.get('interval', 20)} segundos")
        print(f"🎯 Grid: ${self.config.get('max_price', 0.80):.2f} até ${self.config.get('min_price', 0.52):.2f}")
        print(f"📈 Lucro alvo: ${self.config.get('profit_per_trade', 0.05):.2f} por operação")
        print("🛑 Pressione Ctrl+C para parar")
        print("="*70)
        
        # Configuração inicial
        self.is_running = True
        
        try:
            # Limpa ordens existentes no início
            print("\n🔄 Verificando ordens existentes...")
            await self.cancel_all_orders()
            
            # Loop principal
            while self.is_running:
                try:
                    await self.run_grid_cycle()
                    await asyncio.sleep(self.config.get('interval', 20))
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Erro no ciclo: {e}")
                    await asyncio.sleep(10)  # Pausa em caso de erro
                    
        except KeyboardInterrupt:
            print("\n\n🛑 INTERRUPÇÃO SOLICITADA PELO USUÁRIO")
            print("🔴 Parando robô...")
        finally:
            self.is_running = False
            await self.cleanup_before_exit()
    
    async def cleanup_before_exit(self):
        """Limpeza antes de sair"""
        print("\n🧹 Fazendo limpeza final...")
        
        # Opção: cancelar ordens ao sair (comente se não quiser)
        cancel_on_exit = self.config.get('cancel_on_exit', True)
        if cancel_on_exit:
            await self.cancel_all_orders()
        
        print("📊 RESUMO FINAL:")
        print(f"   • Ciclos executados: {self.cycle_count}")
        print(f"   • Ordens criadas: {len(self.orders_history)}")
        print(f"   • Último saldo: ${self.last_balance:.2f}")
        print("\n✅ Robô finalizado com sucesso!")
        print("="*70)


# ========== FUNÇÃO PRINCIPAL ==========
async def main():
    """
    FUNÇÃO PRINCIPAL - AQUI VOCÊ CONFIGURA SEU ROBÔ
    """
    print("⚠️  CONFIGURAÇÃO DO ROBÔ")
    print("="*70)
    
    try:
        # ========== PARTE 1: IMPORTAR SEU CLIENTE ==========
        # DESCOMENTE E CONFIGURE AQUI SEU CLIENTE DO POLYMARKET
        """
        # Exemplo (ajuste conforme sua implementação):
        from polymarket_client import ClobClient
        from config import API_KEY, SECRET_KEY
        
        client = ClobClient(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            testnet=False  # Altere para True para modo teste
        )
        
        # Conecte ao Polymarket
        await client.connect()
        """
        
        # ========== PARTE 2: CONFIGURAÇÕES DO ROBÔ ==========
        config = {
            'interval': 20,               # Segundos entre ciclos
            'quantity': 5,                # Quantidade por ordem
            'max_price': 0.80,            # Preço máximo do grid
            'min_price': 0.52,            # Preço mínimo do grid
            'step': 0.02,                 # Passo entre níveis
            'profit_per_trade': 0.05,     # Lucro alvo por trade
            'max_concurrent_orders': 10,  # Máximo de ordens simultâneas
            'cancel_on_exit': True,       # Cancela ordens ao sair?
        }
        
        print("📋 CONFIGURAÇÃO ATUAL:")
        for key, value in config.items():
            print(f"   • {key}: {value}")
        
        print("\n" + "="*70)
        
        # ========== PARTE 3: VALIDAÇÃO ==========
        print("\n⚠️  IMPORTANTE: Antes de iniciar:")
        print("1. ✅ Cancele TODAS as ordens no Polymarket")
        print("2. ✅ Verifique seu saldo disponível")
        print("3. ✅ Configure seu cliente acima (linhas 324-334)")
        print("4. ✅ Teste primeiro com valores pequenos")
        
        input("\nPressione ENTER para iniciar (ou Ctrl+C para cancelar)...")
        
        # ========== PARTE 4: INICIAR ROBÔ ==========
        # DESCOMENTE QUANDO SEU CLIENTE ESTIVER CONFIGURADO
        """
        bot = PolymarketGridBot(client, config)
        await bot.start()
        """
        
        # Mensagem temporária (REMOVA quando configurar)
        print("\n" + "="*70)
        print("❌ CLIENTE NÃO CONFIGURADO")
        print("="*70)
        print("\nPara usar este robô, você precisa:")
        print("1. Descomentar as linhas 324-334 (importar seu cliente)")
        print("2. Descomentar as linhas 361-362 (criar e iniciar o bot)")
        print("3. Configurar suas chaves API do Polymarket")
        print("\nArquivo salvo como: bot.py (corrigido)")
        
    except KeyboardInterrupt:
        print("\n\n❌ Configuração cancelada pelo usuário")
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")


# ========== EXECUÇÃO ==========
if __name__ == "__main__":
    print("🤖 ROBÔ GRID TRADING - POLYMARKET")
    print("Versão corrigida - Sem duplicação de ordens")
    print("="*70)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Programa encerrado")
