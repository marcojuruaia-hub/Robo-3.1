"""
ROBÔ GRID TRADING CORRIGIDO - SEM DUPLICAÇÃO
"""
import asyncio
import time
from typing import Dict, List
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GridTradingBotCorrigido:
    def __init__(self, client, config: Dict):
        """
        Inicializa o robô grid trading corrigido
        
        Args:
            client: Cliente da API do Polymarket
            config: Configurações do grid
        """
        self.client = client
        self.config = config
        
        # Preços do grid (de 0.80 até 0.52 em decrementos de 0.02)
        self.grid_prices = [round(0.80 - i*0.02, 2) for i in range(15)]
        
        # Controle de ordens já criadas
        self.orders_created = {}
        
        # Status do robô
        self.running = False
        
        logger.info(f"Grid de preços: {self.grid_prices}")
    
    async def get_balance_safe(self):
        """Obtém saldo de forma segura (sem erro _get_headers)"""
        try:
            # Tenta método padrão
            balance = await self.client.get_balance()
            return float(balance)
        except AttributeError as e:
            if '_get_headers' in str(e):
                # Fallback para método alternativo
                try:
                    # Método comum em APIs
                    balance = await self.client.get_account_balance()
                    return float(balance)
                except:
                    # Último fallback
                    try:
                        balance = await self.client.fetch_balance()
                        return float(balance['free'])
                    except:
                        logger.error("Não foi possível obter saldo")
                        return 0.0
            return 0.0
        except Exception as e:
            logger.error(f"Erro ao obter saldo: {e}")
            return 0.0
    
    async def get_open_orders_safe(self):
        """Obtém ordens abertas de forma segura"""
        try:
            orders = await self.client.get_open_orders()
            return orders if orders else []
        except Exception as e:
            logger.error(f"Erro ao obter ordens abertas: {e}")
            return []
    
    async def cancel_all_orders(self):
        """Cancela todas as ordens abertas"""
        try:
            orders = await self.get_open_orders_safe()
            for order in orders:
                await self.client.cancel_order(order['id'])
            logger.info(f"Canceladas {len(orders)} ordens")
            return True
        except Exception as e:
            logger.error(f"Erro ao cancelar ordens: {e}")
            return False
    
    async def has_sufficient_balance(self, price: float, quantity: int = 5):
        """Verifica se tem saldo suficiente para uma ordem"""
        try:
            balance = await self.get_balance_safe()
            required = price * quantity
            
            # Precisa de saldo + 10% para taxas
            if balance >= required * 1.1:
                return True
            else:
                logger.warning(f"Saldo insuficiente: {balance} < {required}")
                return False
        except Exception as e:
            logger.error(f"Erro na verificação de saldo: {e}")
            return False
    
    async def create_order_if_needed(self, price: float):
        """
        Cria ordem apenas se não existir uma no mesmo preço
        e se tiver saldo suficiente
        """
        try:
            # 1. Verifica ordens existentes
            open_orders = await self.get_open_orders_safe()
            
            # 2. Verifica se já existe ordem neste preço
            for order in open_orders:
                if abs(float(order.get('price', 0)) - price) < 0.001:
                    logger.info(f"Já existe ordem em ${price:.2f}")
                    return False
            
            # 3. Verifica saldo
            if not await self.has_sufficient_balance(price):
                return False
            
            # 4. Cria a ordem
            quantity = self.config.get('quantity', 5)
            order_result = await self.client.create_order(
                side='buy',
                price=price,
                quantity=quantity,
                expiration='Until Cancelled'
            )
            
            if order_result and order_result.get('id'):
                logger.info(f"✅ COMPRA criada: {quantity} shares a ${price:.2f}")
                self.orders_created[price] = time.time()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao criar ordem em ${price:.2f}: {e}")
            return False
    
    async def cleanup_old_orders(self, max_age_minutes: int = 5):
        """Cancela ordens muito antigas que não foram executadas"""
        try:
            open_orders = await self.get_open_orders_safe()
            current_time = time.time()
            
            for order in open_orders:
                order_id = order.get('id')
                order_price = float(order.get('price', 0))
                
                # Verifica se a ordem está na nossa lista e é muito antiga
                if order_price in self.orders_created:
                    order_age = current_time - self.orders_created[order_price]
                    if order_age > max_age_minutes * 60:  # Converter para segundos
                        await self.client.cancel_order(order_id)
                        logger.info(f"Cancelada ordem antiga em ${order_price:.2f}")
                        del self.orders_created[order_price]
                        
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
    
    async def run_cycle(self, cycle_number: int):
        """Executa um ciclo completo do grid trading"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 CICLO {cycle_number}")
        logger.info(f"{'='*60}")
        
        # 1. Limpa ordens antigas
        await self.cleanup_old_orders()
        
        # 2. Verifica saldo
        balance = await self.get_balance_safe()
        logger.info(f"💰 Saldo disponível: ${balance:.2f}")
        
        # 3. Verifica ordens abertas
        open_orders = await self.get_open_orders_safe()
        logger.info(f"📊 Compras abertas: {len(open_orders)}")
        
        # 4. Cria ordens do grid
        logger.info("🔵 CRIANDO ORDENS DE COMPRA...")
        orders_created_count = 0
        
        for price in self.grid_prices:
            if await self.create_order_if_needed(price):
                orders_created_count += 1
            
            # Pequena pausa entre ordens
            await asyncio.sleep(0.5)
        
        logger.info(f"📋 RESUMO DO CICLO:")
        logger.info(f"   Ordens de compra criadas: {orders_created_count}")
        logger.info(f"   Ordens abertas totais: {len(open_orders)}")
        
        # 5. Aguarda próximo ciclo
        interval = self.config.get('interval', 20)
        logger.info(f"⏳ Próximo ciclo em {interval} segundos...")
        await asyncio.sleep(interval)
    
    async def start(self):
        """Inicia o robô"""
        logger.info("🚀 INICIANDO ROBÔ CORRIGIDO...")
        logger.info(f"📈 Grid: ${self.grid_prices[0]:.2f} até ${self.grid_prices[-1]:.2f}")
        logger.info(f"⏱️ Intervalo: {self.config.get('interval', 20)} segundos")
        logger.info("🛑 Pressione Ctrl+C para parar")
        
        # Cancela ordens existentes no início
        logger.info("🔄 Cancelando ordens existentes...")
        await self.cancel_all_orders()
        self.orders_created.clear()
        
        # Inicia o loop
        self.running = True
        cycle = 1
        
        try:
            while self.running:
                await self.run_cycle(cycle)
                cycle += 1
        except KeyboardInterrupt:
            logger.info("\n🛑 Robô interrompido pelo usuário")
        finally:
            self.running = False
            logger.info("✅ Robô finalizado")

# USO DO ROBÔ (COMO CHAMAR)
async def main():
    """
    Exemplo de como usar o robô corrigido
    """
    # 1. Importar seu cliente (já existente)
    # from seu_client import ClobClient
    
    # 2. Configurar o cliente (já feito no seu código)
    # client = ClobClient(...)
    
    # 3. Configurações do robô
    config = {
        'interval': 20,  # segundos entre ciclos
        'quantity': 5,   # shares por ordem
        'min_price': 0.52,
        'max_price': 0.80
    }
    
    # 4. Criar e iniciar o robô
    # bot = GridTradingBotCorrigido(client, config)
    # await bot.start()

if __name__ == "__main__":
    print("""
    ⚠️  IMPORTANTE: 
    1. Primeiro cancele todas as ordens no Polymarket
    2. Copie este código para seu arquivo existente
    3. Substitua as funções problemáticas
    
    Use este código como base para corrigir seu robô!
    """)
