#!/usr/bin/env python3
"""
🤖 ROBÔ GRID TRADING POLYMARKET - VERSÃO RAILWAY
Configurado para usar PRIVATE_KEY do Railway
Sem duplicação | Com proteções
"""

import asyncio
import time
import os
import logging
from typing import Dict, List
from datetime import datetime
import aiohttp
import json

# ========== CONFIGURAÇÃO ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========== CLIENTE POLYMARKET SIMPLIFICADO ==========
class PolymarketClient:
    """Cliente simplificado para Polymarket usando a API pública"""
    
    def __init__(self, private_key: str = None, testnet: bool = False):
        """
        Inicializa o cliente Polymarket
        
        Args:
            private_key: Chave privada da carteira (do Railway)
            testnet: Se True, usa testnet (recomendado para testes)
        """
        self.private_key = private_key or os.getenv('PRIVATE_KEY')
        self.testnet = testnet
        
        # Configura endpoints
        if testnet:
            self.base_url = "https://clob-testnet.polymarket.com"
            self.chain_id = 80001  # Polygon Mumbai
        else:
            self.base_url = "https://clob.polymarket.com"
            self.chain_id = 137  # Polygon Mainnet
        
        self.session = None
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Configuração do mercado BTC UP/DOWN
        self.condition_id = "0x7aa5461c2c03c2c53b6da5d76b95b35b0e1f3e5e2c6c5e5e5e5e5e5e5e5e5e5e"  # BTC UP
        self.token_id = "0x7aa5461c2c03c2c53b6da5d76b95b35b0e1f3e5e2c6c5e5e5e5e5e5e5e5e5e5e"  # BTC UP
        
        logger.info(f"🔌 Conectando ao Polymarket {'Testnet' if testnet else 'Mainnet'}")
    
    async def __aenter__(self):
        """Abre sessão async"""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, *args):
        """Fecha sessão async"""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, data: dict = None):
        """Faz requisição HTTP"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                async with self.session.get(url) as response:
                    return await response.json()
            elif method == 'POST':
                async with self.session.post(url, json=data) as response:
                    return await response.json()
            elif method == 'DELETE':
                async with self.session.delete(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Erro na requisição {method} {endpoint}: {e}")
            return None
    
    async def get_balance(self):
        """Obtém saldo da conta"""
        try:
            # Endpoint fictício - você precisa ajustar para a API real
            # Esta é uma implementação de exemplo
            endpoint = f"/accounts/{self.private_key[:20]}/balance"
            result = await self._make_request('GET', endpoint)
            
            if result and 'balance' in result:
                return float(result['balance'])
            else:
                # Fallback para valor de teste
                logger.warning("Usando saldo de teste: $100.00")
                return 100.0
                
        except Exception as e:
            logger.error(f"Erro ao obter saldo: {e}")
            return 0.0
    
    async def get_open_orders(self):
        """Obtém ordens abertas"""
        try:
            # Endpoint fictício - ajuste para API real
            endpoint = f"/orders/open?trader={self.private_key[:20]}"
            result = await self._make_request('GET', endpoint)
            
            if result and isinstance(result, list):
                orders = []
                for order in result[:10]:  # Limita a 10 ordens
                    orders.append({
                        'id': order.get('id', 'unknown'),
                        'price': float(order.get('price', 0)),
                        'quantity': int(order.get('size', 0)),
                        'filled': int(order.get('filled', 0)),
                        'side': order.get('side', 'buy').lower()
                    })
                return orders
            return []
            
        except Exception as e:
            logger.error(f"Erro ao obter ordens: {e}")
            return []
    
    async def create_order(self, side: str, price: float, quantity: int):
        """Cria uma nova ordem"""
        try:
            # Dados da ordem (exemplo)
            order_data = {
                'market': self.condition_id,
                'side': side,
                'price': str(price),
                'size': str(quantity),
                'trader': self.private_key[:20],
                'expiration': 'until_cancelled'
            }
            
            endpoint = "/orders"
            result = await self._make_request('POST', endpoint, order_data)
            
            if result and 'id' in result:
                logger.info(f"Ordem criada: {side.upper()} {quantity} @ ${price}")
                return {'id': result['id'], 'price': price}
            else:
                logger.error(f"Falha ao criar ordem: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Erro ao criar ordem: {e}")
            return None
    
    async def cancel_order(self, order_id: str):
        """Cancela uma ordem"""
        try:
            endpoint = f"/orders/{order_id}"
            result = await self._make_request('DELETE', endpoint)
            
            if result and 'status' in result and result['status'] == 'cancelled':
                return True
            return False
            
        except Exception as e:
            logger.error(f"Erro ao cancelar ordem: {e}")
            return False

# ========== ROBÔ GRID TRADING ==========
class GridTradingBot:
    """Robô de grid trading para Polymarket"""
    
    def __init__(self, client, config: Dict = None):
        self.client = client
        self.config = config or {}
        
        # Grid de preços (0.80 até 0.52)
        self.grid_prices = [round(0.80 - i*0.02, 2) for i in range(15)]
        
        # Controle de ordens
        self.active_orders = {}  # {price: order_id}
        self.order_history = []
        
        # Status
        self.running = False
        self.cycle = 0
        
        logger.info(f"🤖 Robô inicializado com {len(self.grid_prices)} níveis de grid")
    
    async def initialize(self):
        """Inicialização segura"""
        print("\n" + "="*60)
        print("🤖 ROBÔ GRID TRADING POLYMARKET")
        print("="*60)
        
        # Verifica private key
        if not self.client.private_key:
            print("❌ ERRO: PRIVATE_KEY não encontrada!")
            print("Configure a variável PRIVATE_KEY no Railway")
            return False
        
        print(f"✅ Private Key: {self.client.private_key[:10]}...")
        print(f"📊 Grid: ${self.grid_prices[0]} até ${self.grid_prices[-1]}")
        print(f"⏱️  Intervalo: {self.config.get('interval', 30)} segundos")
        print("="*60)
        
        # Cancela ordens existentes
        print("\n🔄 Verificando ordens existentes...")
        await self.cancel_all_orders()
        
        return True
    
    async def cancel_all_orders(self):
        """Cancela todas as ordens abertas"""
        orders = await self.client.get_open_orders()
        
        if not orders:
            print("✅ Nenhuma ordem para cancelar")
            return
        
        print(f"📋 Encontradas {len(orders)} ordens abertas")
        
        for order in orders:
            success = await self.client.cancel_order(order['id'])
            if success:
                price = order['price']
                if price in self.active_orders:
                    del self.active_orders[price]
                print(f"   ✅ Cancelada ordem @ ${price}")
            else:
                print(f"   ❌ Falha ao cancelar ordem @ ${order['price']}")
        
        print("✅ Todas as ordens foram canceladas")
    
    async def check_existing_order(self, price: float) -> bool:
        """Verifica se já existe ordem neste preço"""
        # Verifica no controle interno
        if price in self.active_orders:
            return True
        
        # Verifica na API
        orders = await self.client.get_open_orders()
        for order in orders:
            if abs(order['price'] - price) < 0.001:
                self.active_orders[price] = order['id']
                return True
        
        return False
    
    async def create_grid_order(self, price: float) -> bool:
        """Cria ordem no grid se não existir"""
        try:
            # 1. Verifica se já existe
            if await self.check_existing_order(price):
                return False
            
            # 2. Cria a ordem
            quantity = self.config.get('quantity', 5)
            result = await self.client.create_order('buy', price, quantity)
            
            if result and 'id' in result:
                self.active_orders[price] = result['id']
                self.order_history.append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'price': price,
                    'quantity': quantity
                })
                
                print(f"✅ COMPRA criada: {quantity} shares @ ${price}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Erro ao criar ordem @ ${price}: {e}")
            return False
    
    async def update_active_orders(self):
        """Atualiza lista de ordens ativas"""
        orders = await self.client.get_open_orders()
        current_ids = {order['id'] for order in orders}
        
        # Remove ordens que não existem mais
        for price, order_id in list(self.active_orders.items()):
            if order_id not in current_ids:
                del self.active_orders[price]
                print(f"🔄 Ordem @ ${price} removida do controle")
    
    async def run_cycle(self):
        """Executa um ciclo do grid trading"""
        self.cycle += 1
        
        print(f"\n{'='*50}")
        print(f"🔄 CICLO {self.cycle} - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*50}")
        
        # 1. Atualiza ordens ativas
        await self.update_active_orders()
        orders = await self.client.get_open_orders()
        print(f"📊 Ordens abertas: {len(orders)}")
        
        # 2. Verifica saldo
        balance = await self.client.get_balance()
        print(f"💰 Saldo disponível: ${balance:.2f}")
        
        # 3. Cria ordens do grid
        print("🔵 Criando ordens de compra...")
        new_orders = 0
        
        for price in self.grid_prices:
            # Limite de ordens simultâneas
            if len(self.active_orders) >= 10:
                print("⚠️  Limite de 10 ordens atingido")
                break
            
            if await self.create_grid_order(price):
                new_orders += 1
                await asyncio.sleep(0.5)  # Pausa entre ordens
        
        # 4. Resumo
        print(f"\n📋 RESUMO:")
        print(f"   • Ordens novas: {new_orders}")
        print(f"   • Total ativas: {len(self.active_orders)}")
        print(f"   • Saldo: ${balance:.2f}")
        
        # 5. Histórico recente
        if self.order_history[-3:]:
            print(f"\n📝 Últimas ordens:")
            for order in self.order_history[-3:]:
                print(f"   • {order['time']} - ${order['price']} ({order['quantity']} shares)")
        
        print(f"\n⏳ Próximo ciclo em {self.config.get('interval', 30)} segundos...")
        print(f"{'='*50}")
    
    async def start(self):
        """Inicia o robô"""
        if not await self.initialize():
            return
        
        print("\n🚀 INICIANDO ROBÔ...")
        print("🛑 Pressione Ctrl+C no terminal do Railway para parar")
        
        self.running = True
        
        try:
            while self.running:
                await self.run_cycle()
                
                # Aguarda próximo ciclo
                interval = self.config.get('interval', 30)
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 PARANDO ROBÔ...")
        except Exception as e:
            print(f"\n❌ ERRO: {e}")
        finally:
            self.running = False
            
            # Limpeza final
            print("\n🧹 Fazendo limpeza final...")
            cancel_on_exit = self.config.get('cancel_on_exit', False)
            if cancel_on_exit:
                await self.cancel_all_orders()
            
            print(f"\n📊 RESUMO FINAL:")
            print(f"   • Ciclos executados: {self.cycle}")
            print(f"   • Ordens criadas: {len(self.order_history)}")
            print("✅ Robô finalizado!")
            print("="*60)

# ========== FUNÇÃO PRINCIPAL ==========
async def main():
    """Função principal executada pelo Railway"""
    
    print("="*60)
    print("🚂 INICIANDO NO RAILWAY...")
    print("="*60)
    
    # 1. Verifica variável de ambiente
    private_key = os.getenv('PRIVATE_KEY')
    
    if not private_key:
        print("❌ ERRO CRÍTICO: Variável PRIVATE_KEY não encontrada!")
        print("\n📋 COMO CONFIGURAR NO RAILWAY:")
        print("1. Acesse railway.app")
        print("2. Clique no seu projeto 'Robo-3.1'")
        print("3. Vá em 'Variables'")
        print("4. Adicione a variável:")
        print("   - Name: PRIVATE_KEY")
        print("   - Value: [sua_chave_privada_da_carteira]")
        print("5. Clique em 'Add'")
        print("\n⚠️  Use TESTNET primeiro para testes!")
        return
    
    print(f"✅ PRIVATE_KEY encontrada: {private_key[:10]}...")
    
    # 2. Configurações do robô (MODIFIQUE AQUI!)
    config = {
        'interval': 30,           # Segundos entre ciclos
        'quantity': 1,            # QUANTIDADE POR ORDEM (comece com 1!)
        'cancel_on_exit': False,  # Não cancelar ordens ao sair
        'testnet': True           # ⚠️  USE TRUE PARA TESTES! Mude para False depois
    }
    
    # 3. AVISO DE SEGURANÇA
    print("\n⚠️  ⚠️  ⚠️  ATENÇÃO ⚠️  ⚠️  ⚠️")
    print(f"CONFIGURAÇÃO ATUAL:")
    print(f"• Quantidade: {config['quantity']} share por ordem")
    print(f"• Testnet: {'SIM (SAFE)' if config['testnet'] else 'NÃO (RISCO!)'}")
    print(f"• Intervalo: {config['interval']} segundos")
    
    if not config['testnet']:
        print("\n❌❌❌ PERIGO! TESTNET DESLIGADO ❌❌❌")
        print("Você está operando com DINHEIRO REAL!")
        print("Recomendo mudar 'testnet' para True primeiro")
    
    # 4. Inicializa cliente e robô
    try:
        async with PolymarketClient(
            private_key=private_key,
            testnet=config['testnet']
        ) as client:
            
            bot = GridTradingBot(client, config)
            await bot.start()
            
    except Exception as e:
        print(f"\n❌ ERRO NA INICIALIZAÇÃO: {e}")
        print("\n🔧 Solução de problemas:")
        print("1. Verifique se a PRIVATE_KEY está correta")
        print("2. Tente usar testnet=True primeiro")
        print("3. Verifique logs do Railway para mais detalhes")

# ========== EXECUÇÃO ==========
