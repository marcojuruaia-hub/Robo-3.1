import os
import time
import sys
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OpenOrderParams
from py_clob_client.order_builder.constants import BUY, SELL

# ============================================================================
# CONFIGURAÇÃO DO ROBÔ (EDITAR AQUI)
# ============================================================================
CONFIG = {
    # 🔽 MERCADO ALVO (Bitcoin Up/Down Feb 7, 3PM ET)
    "TOKEN_ID": "58517136834193804262585636069230749276251121320059218806733207887433460217993",  # Use seu scanner para encontrar
    
    # 🔽 PROXY DO POLYMARKET
    "PROXY": "0x658293eF9454A2DD555eb4afcE6436aDE78ab20B",
    
    # 🔽 ESTRATÉGIA DE GRID
    "PRECO_INICIAL": 0.80,      # Começa comprando a 0.80
    "PRECO_FINAL": 0.50,        # Até 0.50
    "INTERVALO_COMPRA": 0.02,   # Espaço entre ordens de compra
    "LUCRO_ALVO": 0.05,         # Lucro por operação
    
    # 🔽 PARÂMETROS OPERACIONAIS
    "SHARES_POR_ORDEM": 5,      # Quantidade por ordem
    "INTERVALO_CICLO": 20,      # 20 segundos entre ciclos
    "MAX_ORDENS_ABERTAS": 10,   # Máximo de ordens abertas simultaneamente
}
# ============================================================================

class RoboGridTrading:
    """Robô de grid trading com compra/venda e lucro fixo"""
    
    def __init__(self, config):
        self.config = config
        self.client = None
        self.ciclo = 0
        
        # Rastreamento de ordens
        self.compras_executadas = {}  # {preco_compra: {qtd, ordem_id, vendida: bool}}
        self.vendas_executadas = {}   # {preco_venda: preco_compra}
        
        print("="*70)
        print(">>> 🤖 ROBÔ GRID TRADING - BITCOIN UP/DOWN <<<")
        print("="*70)
        print(f"Estratégia: Compra de ${config['PRECO_INICIAL']} até ${config['PRECO_FINAL']}")
        print(f"Lucro: ${config['LUCRO_ALVO']} por operação")
        print(f"Intervalo: {config['INTERVALO_CICLO']} segundos")
        print("="*70)
    
    def conectar(self):
        """Conecta ao Polymarket com tratamento de erros"""
        key = os.getenv("PRIVATE_KEY")
        if not key:
            print("❌ ERRO: PRIVATE_KEY não configurada!")
            return False
        
        try:
            # Limpa a chave se necessário
            if key.startswith("0x"):
                key = key[2:]
            
            self.client = ClobClient(
                "https://clob.polymarket.com/",
                key=key,
                chain_id=137,
                signature_type=2,
                funder=self.config["PROXY"]
            )
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            print("✅ Conectado ao Polymarket")
            return True
            
        except Exception as e:
            print(f"❌ Erro na conexão: {e}")
            return False
    
    def obter_saldo_shares(self):
        """Obtém saldo de shares do token"""
        try:
            # Método pode variar conforme versão da biblioteca
            # Tentativa 1: get_balance()
            try:
                saldo_info = self.client.get_balance()
                if isinstance(saldo_info, list):
                    for item in saldo_info:
                        if item.get("tokenId") == self.config["TOKEN_ID"]:
                            return float(item.get("available", 0))
            except:
                pass
            
            # Tentativa 2: Usar API direta (fallback)
            import requests
            headers = self.client._get_headers()
            response = requests.get(
                f"{self.client.api_url}/balances",
                headers=headers
            )
            balances = response.json()
            
            for balance in balances:
                if balance.get("tokenId") == self.config["TOKEN_ID"]:
                    return float(balance.get("available", 0))
            
            return 0
            
        except Exception as e:
            print(f"⚠️ Erro ao ver saldo: {e}")
            return 0
    
    def obter_ordens_do_usuario(self):
        """Obtém todas as ordens do usuário e classifica"""
        try:
            ordens = self.client.get_orders(OpenOrderParams())
            
            compras_abertas = {}
            vendas_abertas = {}
            compras_executadas_temp = {}
            
            for ordem in ordens:
                if ordem.get('asset_id') != self.config["TOKEN_ID"]:
                    continue
                
                preco = round(float(ordem.get('price', 0)), 2)
                lado = ordem.get('side')
                status = ordem.get('status')
                ordem_id = ordem.get('id')
                size_matched = float(ordem.get('size_matched', 0))
                
                if status == 'open':
                    # Ordem ainda aberta
                    if lado == 'BUY':
                        compras_abertas[preco] = {
                            'id': ordem_id,
                            'size': float(ordem.get('size', 0))
                        }
                    elif lado == 'SELL':
                        vendas_abertas[preco] = {
                            'id': ordem_id,
                            'size': float(ordem.get('size', 0))
                        }
                
                elif status in ['filled', 'matched'] and size_matched > 0:
                    # Ordem executada (virou posição)
                    if lado == 'BUY':
                        compras_executadas_temp[preco] = {
                            'quantidade': size_matched,
                            'ordem_id': ordem_id,
                            'vendida': False  # Ainda não foi vendida
                        }
            
            return compras_abertas, vendas_abertas, compras_executadas_temp
            
        except Exception as e:
            print(f"⚠️ Erro ao obter ordens: {e}")
            return {}, {}, {}
    
    def calcular_precos_grid(self):
        """Calcula todos os preços da grid de compra"""
        precos = []
        preco_atual = self.config["PRECO_INICIAL"]
        
        while preco_atual >= self.config["PRECO_FINAL"]:
            precos.append(round(preco_atual, 2))
            preco_atual -= self.config["INTERVALO_COMPRA"]
        
        return precos
    
    def criar_ordem(self, preco, lado, quantidade=None):
        """Cria uma ordem de compra ou venda"""
        if quantidade is None:
            quantidade = self.config["SHARES_POR_ORDEM"]
        
        try:
            ordem = OrderArgs(
                price=preco,
                size=quantidade,
                side=lado,
                token_id=self.config["TOKEN_ID"]
            )
            
            resultado = self.client.create_and_post_order(ordem)
            print(f"✅ {'COMPRA' if lado == BUY else 'VENDA'} criada: {quantidade} shares a ${preco:.2f}")
            return True
            
        except Exception as e:
            erro = str(e).lower()
            if "balance" in erro or "insufficient" in erro:
                print(f"💰 Saldo insuficiente para ordem a ${preco:.2f}")
            elif "already" in erro or "duplicate" in erro:
                print(f"⏭️ Ordem já existe a ${preco:.2f}")
            else:
                print(f"⚠️ Erro na ordem: {str(e)[:50]}")
            return False
    
    def atualizar_compras_executadas(self, novas_compras):
        """Atualiza o dicionário de compras executadas"""
        for preco, info in novas_compras.items():
            if preco not in self.compras_executadas:
                self.compras_executadas[preco] = info
                print(f"📥 Nova posição: Compra executada a ${preco:.2f}")
    
    def executar_ciclo(self):
        """Executa um ciclo completo do robô"""
        self.ciclo += 1
        
        print(f"\n{'='*70}")
        print(f"🔄 CICLO {self.ciclo} - {time.strftime('%H:%M:%S')}")
        print(f"{'='*70}")
        
        # 1. Obtém dados atuais
        saldo_shares = self.obter_saldo_shares()
        compras_abertas, vendas_abertas, novas_compras_exec = self.obter_ordens_do_usuario()
        
        # Atualiza compras executadas
        self.atualizar_compras_executadas(novas_compras_exec)
        
        print(f"💰 Saldo disponível: {saldo_shares:.2f} shares")
        print(f"📊 Compras abertas: {len(compras_abertas)} | Vendas abertas: {len(vendas_abertas)}")
        print(f"📦 Posições compradas: {len(self.compras_executadas)}")
        
        # 2. Calcula grid de compra
        grid_compras = self.calcular_precos_grid()
        
        # 3. ORDENS DE COMPRA: Cria ordens para preços sem compra aberta ou executada
        print(f"\n🔵 CRIANDO ORDENS DE COMPRA...")
        ordens_compra_criadas = 0
        
        for preco_compra in grid_compras:
            # Verifica limites
            if len(compras_abertas) >= self.config["MAX_ORDENS_ABERTAS"]:
                print("   ⏹️ Limite de ordens de compra atingido")
                break
            
            # Já tem compra aberta OU já tem posição nesse preço?
            if preco_compra in compras_abertas or preco_compra in self.compras_executadas:
                continue
            
            # Cria ordem de compra
            if self.criar_ordem(preco_compra, BUY):
                ordens_compra_criadas += 1
                time.sleep(0.5)  # Pequeno delay
            
            if ordens_compra_criadas >= 2:  # Máximo 2 ordens por ciclo
                break
        
        # 4. ORDENS DE VENDA: Para cada posição comprada que ainda não foi vendida
        print(f"\n🟢 CRIANDO ORDENS DE VENDA...")
        ordens_venda_criadas = 0
        
        for preco_compra, info in list(self.compras_executadas.items()):
            # Se já foi vendida, pula
            if info.get('vendida', False):
                continue
            
            preco_venda = round(preco_compra + self.config["LUCRO_ALVO"], 2)
            quantidade = info['quantidade']
            
            # Já tem venda aberta nesse preço?
            if preco_venda in vendas_abertas:
                print(f"   ✅ Já tem venda aberta a ${preco_venda:.2f}")
                continue
            
            # Cria ordem de venda
            print(f"   🎯 Vendendo posição: ${preco_compra:.2f} → ${preco_venda:.2f}")
            if self.criar_ordem(preco_venda, SELL, quantidade):
                ordens_venda_criadas += 1
                time.sleep(0.5)
            
            if ordens_venda_criadas >= 2:  # Máximo 2 ordens por ciclo
                break
        
        # 5. VERIFICA VENDAS EXECUTADAS: Se uma venda foi executada, remove a posição
        # (Isso será detectado no próximo ciclo quando a ordem sumir)
        
        # 6. RE-COMPRA AUTOMÁTICA: Se venda foi executada, pode recomprar
        # Esta lógica será implementada monitorando quando vendas desaparecem
        
        # 7. Mostra resumo
        print(f"\n📋 RESUMO DO CICLO:")
        print(f"   Ordens de compra criadas: {ordens_compra_criadas}")
        print(f"   Ordens de venda criadas: {ordens_venda_criadas}")
        
        if self.compras_executadas:
            print(f"   Posições ativas:")
            for preco, info in sorted(self.compras_executadas.items()):
                status = "✅ Vendida" if info.get('vendida') else "⏳ Aguardando venda"
                print(f"     • ${preco:.2f}: {info['quantidade']} shares ({status})")
        
        # 8. Limpeza: Marca como vendidas as posições que têm venda correspondente executada
        # (Será implementado com verificação de histórico)
        
        return True
    
    def monitorar_vendas_executadas(self):
        """Monitora se vendas foram executadas para liberar re-compra"""
        # Esta função seria chamada periodicamente para verificar
        # se ordens de venda foram executadas
        pass
    
    def iniciar(self):
        """Inicia o robô em loop contínuo"""
        if not self.conectar():
            return
        
        print(f"\n🚀 INICIANDO OPERAÇÃO...")
        print(f"   Intervalo: {self.config['INTERVALO_CICLO']} segundos")
        print(f"   Pressione Ctrl+C para parar")
        print("-"*70)
        
        try:
            while True:
                inicio_ciclo = time.time()
                
                self.executar_ciclo()
                
                # Calcula tempo restante para completar 20 segundos
                tempo_execucao = time.time() - inicio_ciclo
                tempo_espera = max(1, self.config["INTERVALO_CICLO"] - tempo_execucao)
                
                print(f"\n⏳ Próximo ciclo em {tempo_espera:.1f} segundos...")
                time.sleep(tempo_espera)
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 Robô interrompido pelo usuário")
            print(f"   Total de ciclos: {self.ciclo}")
            print(f"   Posições ativas: {len(self.compras_executadas)}")
            
            # Salva estado se quiser continuar depois
            if self.compras_executadas:
                print(f"\n💾 Posições para retomar:")
                for preco, info in self.compras_executadas.items():
                    print(f"   ${preco:.2f}: {info['quantidade']} shares")
        
        except Exception as e:
            print(f"\n❌ ERRO CRÍTICO: {e}")
            import traceback
            traceback.print_exc()

# ============================================================================
# FUNÇÃO AUXILIAR: Encontrar ID do mercado
# ============================================================================
def encontrar_id_mercado():
    """Função para encontrar o ID do mercado automaticamente"""
    import requests
    import re
    
    print("\n" + "="*70)
    print("🔍 BUSCANDO ID DO MERCADO AUTOMATICAMENTE")
    print("="*70)
    
    slug = "bitcoin-up-or-down-february-7-3pm-et"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        for event in data:
            for market in event.get("markets", []):
                if "Bitcoin Up or Down" in market.get("question", ""):
                    token_ids = market.get("clobTokenIds", [])
                    if token_ids:
                        token_id = str(token_ids[0])
                        print(f"✅ ID encontrado: {token_id}")
                        print(f"   Primeiros 15 chars: {token_id[:15]}...")
                        return token_id
        
        print("❌ Mercado não encontrado na API")
        return None
        
    except Exception as e:
        print(f"❌ Erro na busca: {e}")
        return None

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================
if __name__ == "__main__":
    # Verifica se precisa encontrar o ID
    if CONFIG["TOKEN_ID"] == "INSIRA_O_ID_AQUI":
        print("⚠️  Configurando ID do mercado...")
        token_id = encontrar_id_mercado()
        
        if token_id:
            CONFIG["TOKEN_ID"] = token_id
            print(f"\n✅ ID configurado: {token_id[:15]}...")
        else:
            print("\n❌ Não foi possível encontrar o ID do mercado")
            print("   Execute manualmente o scanner ou cole o ID na CONFIG")
            sys.exit(1)
    
    # Cria e inicia o robô
    robo = RoboGridTrading(CONFIG)
    robo.iniciar()
