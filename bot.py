#!/usr/bin/env python3
"""
🤖 ROBÔ GRID TRADING REAL - MAINNET FUNCIONANDO
Igual ao seu bot de vendas, mas com COMPRA + VENDA automática
"""

import os
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

print("=" * 70)
print(">>> 🤖 ROBÔ GRID TRADING REAL - MAINNET FUNCIONANDO <<<")
print("=" * 70)

# ============================================================================
# ⚙️ CONFIGURAÇÃO REAL (EDITA SÓ AQUI)
# ============================================================================
CONFIG = {
    "NOME": "GRID-COMPRA-VENDA-AUTO",
    "TOKEN_ID": "85080102177445047827595824773776292884437000821375292353013080455752528630674",  # BTC UP
    "PROXY": "0x658293eF9454A2DD555eb4afcE6436aDE78ab20B",
    
    # 🔽 ESTRATÉGIA DE COMPRA
    "PRECO_MAX_COMPRA": 0.90,     # Começa comprando a 0.80
    "PRECO_MIN_COMPRA": 0.82,     # Até 0.50
    "INTERVALO_COMPRA": 0.02,     # Espaço entre ordens
    
    # 🔽 ESTRATÉGIA DE VENDA (LUCRO AUTOMÁTICO)
    "LUCRO_FIXO": 0.03,           # Vende com +$0.05 de lucro
    
    # 🔽 CONFIGURAÇÕES PADRÃO
    "SHARES_POR_ORDEM": 5,        # Quantidade por ordem
    "INTERVALO_TEMPO": 120,        # Tempo entre ciclos (segundos)
    "MAX_ORDENS_SIMULTANEAS": 10, # Máximo de ordens abertas
}
# ============================================================================

def criar_grid_compras(config):
    """Cria automaticamente a lista de preços de COMPRA"""
    preco_max = config["PRECO_MAX_COMPRA"]
    preco_min = config["PRECO_MIN_COMPRA"]
    intervalo = config["INTERVALO_COMPRA"]
    
    preco_atual = preco_max
    grid = []
    while preco_atual >= preco_min:
        grid.append(round(preco_atual, 2))
        preco_atual -= intervalo
    
    return grid

def calcular_preco_venda(preco_compra, config):
    """Calcula preço de venda com lucro fixo"""
    return round(preco_compra + config["LUCRO_FIXO"], 2)

def main():
    # 1. Cria grid automaticamente
    CONFIG["GRID_COMPRAS"] = criar_grid_compras(CONFIG)
    
    print(f"🔧 CONFIGURAÇÃO REAL:")
    print(f"   Nome: {CONFIG['NOME']}")
    print(f"   Compra: ${CONFIG['PRECO_MAX_COMPRA']} até ${CONFIG['PRECO_MIN_COMPRA']}")
    print(f"   Lucro: ${CONFIG['LUCRO_FIXO']} por share")
    print(f"   Grid: {len(CONFIG['GRID_COMPRAS'])} preços")
    print(f"   Exemplo: {CONFIG['GRID_COMPRAS'][:3]}...")
    print("-" * 50)
    
    # 2. Conecta ao Polymarket MAINNET (igual seu bot funcional)
    key = os.getenv("PRIVATE_KEY")
    if not key:
        print("❌ ERRO: PRIVATE_KEY não configurada!")
        print("   Railway: Adicione como variável de ambiente")
        return
    
    try:
        # ⭐⭐ CONEXÃO IDÊNTICA AO SEU BOT DE VENDAS QUE FUNCIONA ⭐⭐
        client = ClobClient(
            "https://clob.polymarket.com/",  # MAINNET FUNCIONANDO
            key=key,
            chain_id=137,  # Polygon Mainnet
            signature_type=2,
            funder=CONFIG["PROXY"]
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        print("✅ Conectado ao Polymarket MAINNET (funcionando!)")
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")
        return
    
    # 3. Controle interno SIMPLES mas EFETIVO
    ciclo = 0
    ordens_compra_criadas = []      # Preços onde criamos ordens de COMPRA
    posicoes_compradas = []         # Preços onde a COMPRA foi executada
    ordens_venda_criadas = []       # Preços onde criamos ordens de VENDA
    
    print("\n" + "="*50)
    print("🚀 INICIANDO OPERAÇÃO...")
    print("="*50)
    
    try:
        while True:
            ciclo += 1
            
            print(f"\n{'='*50}")
            print(f"🔄 CICLO {ciclo} - {time.strftime('%H:%M:%S')}")
            print(f"{'='*50}")
            
            # ========== VERIFICA ORDENS EXISTENTES ==========
            ordens_ativas_compras = []
            ordens_ativas_vendas = []
            
            try:
                todas_ordens = client.get_orders()
                
                for ordem in todas_ordens:
                    try:
                        # Converter para dict
                        if hasattr(ordem, '__dict__'):
                            o = ordem.__dict__
                        else:
                            o = dict(ordem)
                        
                        # Verificar token
                        token = o.get('token_id', o.get('asset_id', ''))
                        if token != CONFIG["TOKEN_ID"]:
                            continue
                        
                        preco = float(o.get('price', 0))
                        lado = o.get('side', '').lower()
                        status = o.get('status', '')  # ⭐⭐ CORREÇÃO AQUI! ⭐⭐
                        
                        print(f"🔍 Ordem: {lado} @ ${preco:.2f} - Status: {status}")
                        
                        if lado == 'buy':
                            ordens_ativas_compras.append(preco)
                            
                            # ⭐⭐ DETECTA ORDEM EXECUTADA DE 3 FORMAS ⭐⭐
                            ordem_executada = False
                            
                            # 1. Pelo status
                            if status in ['filled', 'closed', 'executed']:
                                ordem_executada = True
                                print(f"🎯 Status indica EXECUTADA: {status}")
                            
                            # 2. Pela quantidade preenchida (filled_amount)
                            filled = float(o.get('filled', 0))
                            size = float(o.get('size', o.get('amount', 0)))
                            
                            if size > 0 and filled >= size:
                                ordem_executada = True
                                print(f"🎯 Quantidade EXECUTADA: {filled}/{size}")
                            
                            # 3. Se não tem mais a ordem ativa mas estava na nossa lista
                            if preco in ordens_compra_criadas and preco not in ordens_ativas_compras:
                                ordem_executada = True
                                print(f"🎯 Ordem removida da lista ativa (provavelmente executada)")
                            
                            if ordem_executada and preco not in posicoes_compradas:
                                print(f"🚨🚨🚨 COMPRA EXECUTADA DETECTADA: ${preco:.2f} 🚨🚨🚨")
                                posicoes_compradas.append(preco)
                                
                        elif lado == 'sell':
                            ordens_ativas_vendas.append(preco)
                            
                    except Exception as e:
                        print(f"⚠️  Erro ao processar ordem: {e}")
                        continue
                
                print(f"📊 Ordens ativas: {len(ordens_ativas_compras)} compras, {len(ordens_ativas_vendas)} vendas")
                
            except Exception as e:
                print(f"⚠️  Erro ao ver ordens: {e}")
            
            # ========== CRIA VENDAS PARA COMPRAS EXECUTADAS ==========
            vendas_criadas_este_ciclo = 0
            for preco_compra in posicoes_compradas[:]:  # Copia da lista
                # Se já criamos venda para esta compra, pular
                if preco_compra in ordens_venda_criadas:
                    continue
                
                # Limite de vendas por ciclo
                if vendas_criadas_este_ciclo >= 2:
                    break
                
                # Calcular preço de venda
                preco_venda = calcular_preco_venda(preco_compra, CONFIG)
                
                # Verificar se já existe venda neste preço
                if preco_venda in ordens_ativas_vendas:
                    print(f"⏭️  Venda já existe para compra @ ${preco_compra:.2f}")
                    ordens_venda_criadas.append(preco_compra)
                    continue
                
                # Criar ordem de VENDA
                print(f"\n💰💰💰 CRIANDO VENDA AUTOMÁTICA!")
                print(f"   Compra executada: ${preco_compra:.2f}")
                print(f"   Preço venda: ${preco_venda:.2f}")
                print(f"   Lucro por share: ${CONFIG['LUCRO_FIXO']}")
                print(f"   Lucro total: ${CONFIG['LUCRO_FIXO'] * CONFIG['SHARES_POR_ORDEM']:.2f}")
                
                try:
                    ordem_venda = OrderArgs(
                        price=preco_venda,
                        size=CONFIG["SHARES_POR_ORDEM"],
                        side=SELL,
                        token_id=CONFIG["TOKEN_ID"]
                    )
                    
                    client.create_and_post_order(ordem_venda)
                    ordens_venda_criadas.append(preco_compra)
                    vendas_criadas_este_ciclo += 1
                    
                    print(f"   ✅✅✅ VENDA CRIADA COM SUCESSO!")
                    
                    time.sleep(2)  # Pausa maior entre vendas
                    
                except Exception as e:
                    erro = str(e).lower()
                    if "already" in erro or "duplicate" in erro:
                        print(f"   ⏭️  Venda já existe")
                        ordens_venda_criadas.append(preco_compra)
                    elif "balance" in erro or "insufficient" in erro:
                        print(f"   ❌ Sem saldo (shares) para vender")
                    else:
                        print(f"   ❌ Erro na venda: {str(e)[:100]}...")
            
            # ========== CRIA NOVAS ORDENS DE COMPRA ==========
            print(f"\n🔵 VERIFICANDO GRID DE COMPRAS...")
            novas_compras = 0
            
            for preco in CONFIG["GRID_COMPRAS"]:
                # Limite de ordens simultâneas
                total_ordens = len(ordens_ativas_compras) + len(ordens_ativas_vendas)
                if total_ordens >= CONFIG["MAX_ORDENS_SIMULTANEAS"]:
                    print(f"⚠️  Limite de {CONFIG['MAX_ORDENS_SIMULTANEAS']} ordens atingido")
                    break
                
                # Se já temos ordem neste preço, pular
                if preco in ordens_ativas_compras or preco in ordens_compra_criadas:
                    continue
                
                # Tentar criar ordem de COMPRA
                print(f"🎯 Tentando COMPRA a ${preco:.2f}...")
                
                try:
                    ordem_compra = OrderArgs(
                        price=preco,
                        size=CONFIG["SHARES_POR_ORDEM"],
                        side=BUY,
                        token_id=CONFIG["TOKEN_ID"]
                    )
                    
                    client.create_and_post_order(ordem_compra)
                    ordens_compra_criadas.append(preco)
                    novas_compras += 1
                    
                    print(f"✅ COMPRA criada: {CONFIG['SHARES_POR_ORDEM']} shares @ ${preco:.2f}")
                    
                    # Pausa e limite
                    time.sleep(1)
                    if novas_compras >= 2:  # Máximo 2 novas por ciclo
                        break
                    
                except Exception as e:
                    erro = str(e).lower()
                    if "balance" in erro or "insufficient" in erro:
                        print(f"💰 Sem saldo para ${preco:.2f}")
                        break
                    elif "already" in erro or "duplicate" in erro:
                        print(f"⏭️  Já existe ordem a ${preco:.2f}")
                        ordens_compra_criadas.append(preco)
                    else:
                        print(f"⚠️  Erro: {str(e)[:50]}...")
            
            # ========== RESUMO DO CICLO ==========
            print(f"\n📋 RESUMO DO CICLO {ciclo}:")
            print(f"   • Compras criadas: {len(ordens_compra_criadas)}")
            print(f"   • Compras executadas: {len(posicoes_compradas)}")
            print(f"   • Vendas criadas: {len(ordens_venda_criadas)}")
            print(f"   • Novas ordens este ciclo: {novas_compras}")
            
            # Mostrar situação atual
            if ordens_compra_criadas:
                print(f"\n🛒 NOSSAS COMPRAS:")
                for preco in sorted(ordens_compra_criadas, reverse=True)[:8]:
                    if preco in posicoes_compradas:
                        if preco in ordens_venda_criadas:
                            status = "💰 VENDA CRIADA"
                        else:
                            status = "🎯 EXECUTADA (aguardando venda)"
                    elif preco in ordens_ativas_compras:
                        status = "⏳ AGUARDANDO EXECUÇÃO"
                    else:
                        status = "❓ STATUS DESCONHECIDO"
                    print(f"   • ${preco:.2f} - {status}")
            
            if posicoes_compradas:
                print(f"\n💰 POSIÇÕES EXECUTADAS:")
                for preco_compra in posicoes_compradas[:5]:
                    if preco_compra in ordens_venda_criadas:
                        preco_venda = calcular_preco_venda(preco_compra, CONFIG)
                        lucro = CONFIG["LUCRO_FIXO"] * CONFIG["SHARES_POR_ORDEM"]
                        print(f"   • Compra ${preco_compra:.2f} → Venda ${preco_venda:.2f} (+${lucro:.2f})")
                    else:
                        print(f"   • Compra ${preco_compra:.2f} → ⏳ Aguardando criação de venda")
            
            # ========== AGUARDAR PRÓXIMO CICLO ==========
            print(f"\n⏳ Próximo ciclo em {CONFIG['INTERVALO_TEMPO']} segundos...")
            print(f"{'='*50}")
            time.sleep(CONFIG["INTERVALO_TEMPO"])
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*50}")
        print("🛑 ROBÔ PARADO PELO USUÁRIO")
        print(f"{'='*50}")
        print(f"📊 RESUMO FINAL:")
        print(f"   • Total de ciclos: {ciclo}")
        print(f"   • Compras criadas: {len(ordens_compra_criadas)}")
        print(f"   • Compras executadas: {len(posicoes_compradas)}")
        print(f"   • Vendas criadas: {len(ordens_venda_criadas)}")
        print(f"{'='*50}")
        
        # Mostrar situação financeira
        if posicoes_compradas:
            print(f"\n💰 LUCRO POTENCIAL:")
            total_lucro = 0
            for preco_compra in posicoes_compradas:
                if preco_compra in ordens_venda_criadas:
                    lucro = CONFIG["LUCRO_FIXO"] * CONFIG["SHARES_POR_ORDEM"]
                    total_lucro += lucro
                    print(f"   • Compra ${preco_compra:.2f}: +${lucro:.2f}")
            print(f"   📈 TOTAL: +${total_lucro:.2f}")
        
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
